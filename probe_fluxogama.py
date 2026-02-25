"""Probe Fluxogama API - write results to file directly."""
import os, json, ssl, sys, base64
import urllib.request, urllib.error

from dotenv import load_dotenv
load_dotenv('.env.local')

base_url = os.environ.get('FLUXOGAMA_BASE_URL', '')
chave = os.environ.get('FLUXOGAMA_CHAVE', '')
oaz_chave = os.environ.get('OAZ_CHAVE', '')

out = open('probe_output.txt', 'w', encoding='utf-8')

def log(msg):
    out.write(msg + '\n')
    out.flush()

# Decode OAZ_CHAVE
try:
    oaz_decoded = json.loads(base64.b64decode(oaz_chave + '==='))
    log(f"OAZ_CHAVE decoded: {json.dumps(oaz_decoded)}")
except:
    log("OAZ_CHAVE: not base64")

ctx = ssl.create_default_context()
flux_headers = {
    'Authorization': f'Bearer {chave}',
    'Content-Type': 'application/json; charset=utf-8',
    'Accept': 'application/json',
}

def probe(method, url, headers, label, body=None):
    log(f"\n--- {label} ---")
    log(f"  {method} {url}")
    try:
        data = json.dumps(body).encode('utf-8') if body else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            rbody = resp.read().decode('utf-8')
            log(f"  -> {resp.status} OK")
            log(f"  -> Body: {rbody[:800]}")
            return resp.status
    except urllib.error.HTTPError as e:
        ebody = ''
        try: ebody = e.read().decode('utf-8')
        except: pass
        log(f"  -> {e.code} {e.reason}")
        log(f"  -> Body: {ebody[:500]}")
        return e.code
    except Exception as e:
        log(f"  -> ERROR: {e}")
        return None

log("=== PROBING FLUXOGAMA API ===")

# GET endpoints
for path, label in [
    ('/rest/api/v1/modelo', 'GET modelo'),
    ('/rest/api/v1/remessa/modelo', 'GET remessa/modelo'),
    ('/rest/api/v1/modelos', 'GET modelos'),
    ('/rest/api/v1/remessa', 'GET remessa'),
    ('/rest/api/v1/modelo?referencia=OAZ-REF-001', 'GET modelo by ref'),
    ('/rest/api/v1/modelo?colecao=VERAO+2026', 'GET modelo by colecao'),
]:
    probe('GET', f'{base_url}{path}', flux_headers, label)

# POST as array (remessa pattern)
log("\n=== POST AS ARRAY (remessa pattern) ===")
test_arr = [{
    "referencia": "TEST-PROBE-001",
    "colecao": "TESTE",
    "uno.1": "Teste probe",
}]
probe('POST', f'{base_url}/rest/api/v1/remessa/modelo', flux_headers, 'POST array', body=test_arr)

# POST single object
log("\n=== POST SINGLE OBJECT ===")
probe('POST', f'{base_url}/rest/api/v1/remessa/modelo', flux_headers, 'POST single', body=test_arr[0])

out.close()
print("Done - see probe_output.txt")
