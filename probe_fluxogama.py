"""Probe Fluxogama API to discover available endpoints and list models."""
import os, json, ssl, sys, base64
import urllib.request, urllib.error

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv('.env.local')

base_url = os.environ.get('FLUXOGAMA_BASE_URL', '')
chave = os.environ.get('FLUXOGAMA_CHAVE', '')

# Also check the OAZ_ credentials (different auth?)
oaz_base = os.environ.get('OAZ_BASE_URL', '')
oaz_chave = os.environ.get('OAZ_CHAVE', '')

print("=== CREDENTIALS ===")
print(f"FLUXOGAMA_BASE_URL: {base_url}")
print(f"FLUXOGAMA_CHAVE:    {chave[:30]}...")
print(f"OAZ_BASE_URL:       {oaz_base}")
print(f"OAZ_CHAVE:          {oaz_chave[:30]}...")

# Decode OAZ_CHAVE (it looks like base64 JSON, not JWT)
try:
    oaz_decoded = json.loads(base64.b64decode(oaz_chave + '==='))
    print(f"OAZ_CHAVE decoded:  {json.dumps(oaz_decoded, indent=2)}")
except:
    print("OAZ_CHAVE: not base64 JSON")

print()

ctx = ssl.create_default_context()

def probe(method, url, headers, label, body=None):
    """Try an endpoint and print the result."""
    print(f"--- {label} ---")
    print(f"  {method} {url}")
    try:
        data = json.dumps(body).encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            rbody = resp.read().decode('utf-8')
            print(f"  -> {resp.status} OK")
            print(f"  -> Body (first 500 chars): {rbody[:500]}")
            return resp.status, rbody
    except urllib.error.HTTPError as e:
        ebody = ''
        try:
            ebody = e.read().decode('utf-8')
        except:
            pass
        print(f"  -> {e.code} {e.reason}")
        print(f"  -> Body: {ebody[:300]}")
        return e.code, ebody
    except Exception as e:
        print(f"  -> ERROR: {e}")
        return None, str(e)

# Headers for FLUXOGAMA (Bearer JWT)
flux_headers = {
    'Authorization': f'Bearer {chave}',
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json',
}

# Headers for OAZ (different auth - chave param?)
oaz_headers = {
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json',
}

print("=" * 60)
print(" PROBING WITH FLUXOGAMA_CHAVE (Bearer JWT)")
print("=" * 60)

# Try GET endpoints to find models
endpoints = [
    ('GET', '/rest/api/v1/modelo', 'List models'),
    ('GET', '/rest/api/v1/remessa/modelo', 'List remessa/modelo'),
    ('GET', '/rest/api/v1/modelos', 'List modelos'),
    ('GET', '/rest/api/v1/remessa', 'List remessas'),
    ('GET', '/rest/api/v1/catalogo/modelo', 'Catalogo modelo'),
    ('GET', '/rest/api/v1/produto', 'List produtos'),
    ('GET', '/rest/api/v1/produtos', 'List produtos (plural)'),
]

for method, path, label in endpoints:
    url = f"{base_url}{path}"
    probe(method, url, flux_headers, label)
    print()

# Try POST with id field
print("=" * 60)
print(" TRYING POST WITH 'referencia' AS LOOKUP KEY")
print("=" * 60)
# Maybe the API can create if we structure payload differently
# Try wrapping in array (remessa = batch)
test_payload = [
    {
        "referencia": "TEST-PROBE-001",
        "colecao": "TESTE",
        "uno.1": "Teste de probe",
    }
]
probe('POST', f'{base_url}/rest/api/v1/remessa/modelo', flux_headers,
      'POST array payload', body=test_payload)
print()

# Also try as single object
probe('POST', f'{base_url}/rest/api/v1/remessa/modelo', flux_headers,
      'POST single object', body=test_payload[0])
