"""Fetch the Bearer-auth version of /retorno/modelo (4.4KB) for format clues,
then try querying with the correct filter format."""
import httpx
import json

TOKEN = "eyJhbGciOiJIUzM4NCJ9.eyJzdWIiOiI5NSIsImlzcyI6Imh0dHBzOi8vb2F6LmZsdXhvZ2FtYS5jb20uYnIvcmVzdC9hcGkvdjEvYXV0ZW50aWNhY2FvIiwiaWF0IjoxNzcxOTU1OTc3LCJleHAiOjE3NzIwMDk5Nzd9.j9EF8htvH8nTU7LmAXRI_Eq7sdQON6GY9rdHrqHdsLOLkuufAs5OFG0IlB9UmDLx"
BASE = "https://oaz.fluxogama.com.br"
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

# Get the 4.4KB Bearer page (probably a form/instructions)
print("=== Bearer GET /retorno/modelo (4.4KB) ===")
r = httpx.get(f"{BASE}/rest/api/v1/retorno/modelo", headers=H, timeout=15)
print(r.text)
print("=== END ===\n")

# Based on the Java error "VORetornoFiltroCampos":
# The VO (Value Object) probably has fields: campo, operador, valor
# And the request body probably has: campos (VORetornoFiltroCampos), listas (something)
# The error said "from Array value" when I sent a list, meaning campos must be an OBJECT
# But when I sent an object {campo: value} it said "at least 1 campo or 1 lista"
# 
# My theory: VORetornoFiltroCampos is the CONTAINER object, not a filter spec
# It probably has fields like:
#   campos: { "modelo.id": "= 1", "modelo.referencia": "like %TEST%" }
#   listas: ["cor", "ficha"]
#
# Wait - the error says VORetornoFiltroCampos cannot be deserialized from Array
# when I sent campos as a list. So campos IS the VORetornoFiltroCampos object.
# And the check "at least 1 campo or 1 lista" means:
# - VORetornoFiltroCampos has two map fields: "campos" and "listas"
# - At runtime, at least one key must exist in either map
# 
# So the real structure is probably:
# VORetornoFiltroCampos {
#   Map<String, String> campos;  // field filters
#   Map<String, ?> listas;       // related data to include
# }
#
# But the top-level JSON IS the VORetornoFiltroCampos
# So body = { "campos": {field: filter_expr}, "listas": {...} }
# But I already tried that and it said "at least 1 campo or 1 lista"
# Which means the maps were empty after deserialization
#
# Maybe the issue is that the field names contain dots (modelo.id)
# and Jackson might be interpreting them as nested paths
# Let me try without dots or with escaping

print("=== Testing various formats ===")

bodies = [
    # Try flat field names without dots
    {"campos": {"id": "> 0"}},
    # Try nested
    {"campos": {"modelo": {"id": "> 0"}}},
    # Try with listas as a map of strings
    {"listas": {"cor": ""}},
    {"listas": {"cor": "= 1"}},
    {"listas": {"ficha": ""}},
    # Try both
    {"campos": {"id": "> 0"}, "listas": {"cor": ""}},
    # Try with un-dotted field
    {"campos": {"fg_status": "= 1"}},
    # Try with modelo prefix
    {"campos": {"modelo": "> 0"}},
]

for body in bodies:
    r = httpx.post(f"{BASE}/rest/api/v1/retorno/modelo", 
                   json=body, headers=H, timeout=15)
    ct = r.headers.get("content-type", "")
    is_json = r.text.strip()[:1] in ("{", "[")
    status_text = f"Status: {r.status_code}"
    if is_json:
        try:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                status_text += f" SUCCESS! {len(data)} items"
            else:
                status_text += f" {json.dumps(data, ensure_ascii=False)[:150]}"
        except:
            status_text += f" raw: {r.text[:150]}"
    else:
        status_text += f" text: {r.text[:150]}"
    print(f"  Body={json.dumps(body)[:60]:60s} | {status_text}")
