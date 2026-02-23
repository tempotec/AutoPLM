"""Check which uno-mapped fields are filled in ficha_tecnica_item."""
import psycopg2

DEV_URL = "postgresql://neondb_owner:npg_mNdSqh3Z8fgB@ep-cold-sea-ad0fxv9k.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
conn = psycopg2.connect(DEV_URL)
cur = conn.cursor()

# Check how many fichas/items exist
cur.execute("SELECT COUNT(*) FROM ficha_tecnica")
fichas = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM ficha_tecnica_item")
items = cur.fetchone()[0]
print(f"Fichas: {fichas}  |  Items: {items}\n")

if items == 0:
    print("Nenhum item de ficha encontrado no banco dev.")
    cur.close(); conn.close()
    exit()

# DB fields that map to uno
db_fields = {
    'linha':       'uno.10 (Linha)',
    'grupo':       'uno.11 (Grupo)',
    'sub_grupo':   'uno.12 (Sub Grupo)',
    'material_composition_percentage': 'uno.24 (Material Principal)',
    'ncm':         'uno.50 (NCM)',
    'familia':     'uno.300 (Família)',
}

# Check columns exist
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ficha_tecnica_item' ORDER BY ordinal_position")
columns = [r[0] for r in cur.fetchall()]

print("=== Campos DB (uno) nas fichas ===")
for field, label in db_fields.items():
    if field not in columns:
        print(f"  {label:40s} ❌ coluna não existe na tabela")
        continue
    cur.execute(f"SELECT COUNT(*) FROM ficha_tecnica_item WHERE {field} IS NOT NULL AND {field} != ''")
    filled = cur.fetchone()[0]
    pct = (filled / items * 100) if items > 0 else 0
    cur.execute(f"SELECT DISTINCT {field} FROM ficha_tecnica_item WHERE {field} IS NOT NULL AND {field} != '' LIMIT 5")
    examples = [r[0] for r in cur.fetchall()]
    status = "✅" if filled > 0 else "⚠️"
    print(f"  {label:40s} {status} {filled}/{items} ({pct:.0f}%)  ex: {examples}")

# Also check text fields
print("\n=== Campos texto (uno) nas fichas ===")
text_fields = {
    'description_item': 'uno.1 (Descrição)',
    'item_no_ref_supplier': 'uno.16 (Ref Fornecedor)',
    'obs': 'uno.443 (Observações)',
    'oaz_reference': 'referencia (Ref OAZ)',
}
for field, label in text_fields.items():
    if field not in columns:
        print(f"  {label:40s} ❌ coluna não existe")
        continue
    cur.execute(f"SELECT COUNT(*) FROM ficha_tecnica_item WHERE {field} IS NOT NULL AND {field} != ''")
    filled = cur.fetchone()[0]
    pct = (filled / items * 100) if items > 0 else 0
    status = "✅" if filled > 0 else "⚠️"
    print(f"  {label:40s} {status} {filled}/{items} ({pct:.0f}%)")

# Check oaz_value_map coverage
print("\n=== Cobertura De/Para (oaz_value_map) ===")
for field, label in db_fields.items():
    if field not in columns:
        continue
    uno_key = label.split('(')[0].strip()
    cur.execute(f"""
        SELECT DISTINCT i.{field} 
        FROM ficha_tecnica_item i 
        WHERE i.{field} IS NOT NULL AND i.{field} != ''
    """)
    distinct_values = [r[0] for r in cur.fetchall()]
    if not distinct_values:
        continue
    
    matched = 0
    unmatched = []
    for val in distinct_values:
        import unicodedata, re
        norm = unicodedata.normalize('NFKD', str(val))
        norm = ''.join(c for c in norm if not unicodedata.combining(c)).strip().upper()
        norm = re.sub(r'\s+', ' ', norm)
        cur.execute("SELECT wsid_value FROM oaz_value_map WHERE field_key=%s AND text_norm=%s", (uno_key, norm))
        row = cur.fetchone()
        if row:
            matched += 1
        else:
            unmatched.append(val)
    
    total = len(distinct_values)
    print(f"  {label}: {matched}/{total} valores resolvem WSID")
    if unmatched[:3]:
        print(f"    Sem WSID: {unmatched[:3]}")

cur.close()
conn.close()
