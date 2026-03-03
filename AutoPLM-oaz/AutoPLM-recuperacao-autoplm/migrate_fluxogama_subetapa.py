"""
Migração: Adicionar coluna fluxogama_subetapa à tabela specification

Executar: python migrate_fluxogama_subetapa.py
"""
import os
import sys

# Load env
env_path = os.path.join(os.path.dirname(__file__), '.env.local')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("❌ DATABASE_URL não configurada.")
    sys.exit(1)

try:
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Check if column already exists
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name='specification' AND column_name='fluxogama_subetapa'
    """)
    if cur.fetchone():
        print("ℹ️ Coluna 'fluxogama_subetapa' já existe. Nada a fazer.")
    else:
        cur.execute("ALTER TABLE specification ADD COLUMN fluxogama_subetapa VARCHAR(20)")
        conn.commit()
        print("✅ Coluna 'fluxogama_subetapa' adicionada à tabela 'specification'.")

    conn.close()
except Exception as e:
    print(f"❌ Erro: {e}")
    sys.exit(1)
