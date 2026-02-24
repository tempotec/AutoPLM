"""Parse the /retorno/modelo schema HTML and test querying models."""
import httpx
import json
import re
from html.parser import HTMLParser

# Read saved HTML
with open("flux_retorno_raw.html", "r", encoding="utf-8") as f:
    html = f.read()

# Extract table rows with field info
print("=" * 70)
print("EXTRACTING FIELD DOCUMENTATION FROM SCHEMA HTML")
print("=" * 70)

# Find all field names (they appear as td content like "modelo.id", "modelo.referencia", etc.)
field_pattern = r'<td[^>]*>([a-z]+\.[a-z._]+)</td>'
fields = re.findall(field_pattern, html, re.IGNORECASE)
unique_fields = sorted(set(fields))
print(f"\nFound {len(unique_fields)} unique fields:")
for f in unique_fields[:50]:
    print(f"  {f}")
if len(unique_fields) > 50:
    print(f"  ... and {len(unique_fields) - 50} more")

# Look for 'modelo.' prefixed fields specifically  
modelo_fields = [f for f in unique_fields if f.startswith('modelo.')]
print(f"\n--- modelo.* fields ({len(modelo_fields)}) ---")
for f in modelo_fields:
    print(f"  {f}")

# Now try POST /retorno/modelo to query models
print("\n" + "=" * 70)
print("TESTING POST /retorno/modelo TO QUERY MODELS")
print("=" * 70)

TOKEN = "eyJhbGciOiJIUzM4NCJ9.eyJzdWIiOiI5NSIsImlzcyI6Imh0dHBzOi8vb2F6LmZsdXhvZ2FtYS5jb20uYnIvcmVzdC9hcGkvdjEvYXV0ZW50aWNhY2FvIiwiaWF0IjoxNzcxOTU1OTc3LCJleHAiOjE3NzIwMDk5Nzd9.j9EF8htvH8nTU7LmAXRI_Eq7sdQON6GY9rdHrqHdsLOLkuufAs5OFG0IlB9UmDLx"
BASE = "https://oaz.fluxogama.com.br"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# Try different query formats
tests = [
    # Empty body (list all?)
    ("POST empty list", []),
    # With pagination-like params
    ("POST with limit", {"limit": 5}),
    # With filter
    ("POST with filter obj", {"modelo.id": "> 0"}),
    # Array with empty filter
    ("POST array empty filter", [{}]),
    # Array with filter
    ("POST array with filter", [{"campo": "modelo.id", "operador": ">", "valor": "0"}]),
]

for label, body in tests:
    print(f"\n  [{label}]")
    r = httpx.post(
        f"{BASE}/rest/api/v1/retorno/modelo",
        json=body,
        headers=HEADERS,
        timeout=15,
    )
    ct = r.headers.get("content-type", "")
    is_json = "json" in ct or r.text.strip()[:1] in ("{", "[")
    print(f"  Status: {r.status_code}, Type: {'JSON' if is_json else 'HTML'}, Len: {len(r.text)}")
    if is_json:
        try:
            data = r.json()
            if isinstance(data, list):
                print(f"  Array: {len(data)} items")
                if data:
                    print(f"  Keys: {list(data[0].keys())[:15]}")
                    print(f"  First: {json.dumps(data[0], ensure_ascii=False)[:400]}")
            else:
                print(f"  {json.dumps(data, ensure_ascii=False)[:400]}")
        except:
            print(f"  Raw: {r.text[:300]}")
    else:
        print(f"  HTML preview: {r.text[:200]}")
