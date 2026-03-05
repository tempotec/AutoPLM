"""
Test /retorno/modelo with CORRECT Postman format!
Key: campos.campos (plural!) not campos.campo (singular)
+ filtros uses campo/operador/valor (Portuguese)
"""
import json, os, ssl, sys, urllib.request, urllib.error

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip().replace('\r','')
            if not line or line.startswith('#'): continue
            if '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE_URL = os.environ.get('OAZ_BASE_URL', '').rstrip('/')
USUARIO = os.environ.get('OAZ_USUARIO', '')
SENHA = os.environ.get('OAZ_SENHA', '')
ctx = ssl.create_default_context()

# Auth
auth_body = json.dumps({"chave": 1, "usuario": USUARIO, "senha": SENHA}).encode('utf-8')
req = urllib.request.Request(f'{BASE_URL}/autenticacao', data=auth_body, method='POST',
    headers={'Content-Type':'application/json','Accept':'application/json'})
token = None
try:
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        data = json.loads(resp.read().decode('utf-8'))
        ret = data.get('retorno', {})
        if isinstance(ret, dict): token = ret.get('token')
except: pass
if not token: sys.exit(1)
print(f"Auth OK: token={token[:30]}...")

url = f'{BASE_URL}/retorno/modelo'
results = {}

# Test 1: Exact Postman format
test1 = {
    "pagina": 1,
    "campos": {
        "campos": [
            "modelo.id",
            "modelo.ds_referencia",
            "modelo.ws_id",
            "modelo.fg_status",
            "colecao.id",
            "colecao.ds_colecao"
        ]
    },
    "filtros": [
        {
            "campo": "modelo.ds_referencia",
            "operador": "=",
            "valor": "S27TH033"
        }
    ]
}

# Test 2: Get all recent models
test2 = {
    "pagina": 1,
    "campos": {
        "campos": [
            "modelo.id",
            "modelo.ds_referencia",
            "modelo.ws_id",
            "colecao.ds_colecao"
        ]
    },
    "filtros": [
        {
            "campo": "modelo.fg_status",
            "operador": "=",
            "valor": "3"
        }
    ]
}

# Test 3: Find by ws_id (our spec IDs)
test3 = {
    "pagina": 1,
    "campos": {
        "campos": [
            "modelo.id",
            "modelo.ds_referencia",
            "modelo.ws_id"
        ]
    },
    "filtros": [
        {
            "campo": "modelo.ws_id",
            "operador": "is not null"
        }
    ]
}

tests = {"find_S27TH033": test1, "status_3": test2, "wsid_not_null": test3}

for name, body_data in tests.items():
    print(f"\n--- {name} ---")
    body = json.dumps(body_data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST',
        headers={'Content-Type':'application/json','Accept':'application/json','Authorization':f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            raw = resp.read().decode('utf-8')
            entry = {'status': resp.status}
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    entry['type'] = 'dict'
                    entry['keys'] = list(parsed.keys())
                    # Check for data inside
                    for k in parsed:
                        if isinstance(parsed[k], list):
                            entry[f'{k}_count'] = len(parsed[k])
                            if parsed[k] and isinstance(parsed[k][0], dict):
                                entry[f'{k}_keys'] = list(parsed[k][0].keys())
                                entry[f'{k}_first'] = {kk: str(vv)[:100] for kk, vv in list(parsed[k][0].items())[:15]}
                        elif isinstance(parsed[k], (int, float, str, bool)):
                            entry[k] = parsed[k]
                elif isinstance(parsed, list):
                    entry['type'] = 'list'
                    entry['count'] = len(parsed)
                    if parsed and isinstance(parsed[0], dict):
                        entry['keys'] = list(parsed[0].keys())
                        entry['first'] = {k: str(v)[:100] for k, v in list(parsed[0].items())[:15]}
                entry['preview'] = json.dumps(parsed, ensure_ascii=False)[:3000]
            except:
                entry['raw'] = raw[:500]
            results[name] = entry
            print(f"  HTTP {resp.status} | type={entry.get('type')} | keys={entry.get('keys', [])}")
            if 'count' in entry: print(f"  count={entry['count']}")
            if 'first' in entry: print(f"  first={json.dumps(entry['first'], ensure_ascii=False)[:200]}")
            for k in entry:
                if k.endswith('_count'): print(f"  {k}={entry[k]}")
                if k.endswith('_first'): print(f"  {k}={json.dumps(entry[k], ensure_ascii=False)[:200]}")
    except urllib.error.HTTPError as e:
        err = ''
        try: err = e.read().decode('utf-8')[:500]
        except: pass
        results[name] = {'status': e.code, 'error': e.reason, 'body': err}
        print(f"  HTTP {e.code} | {err[:200]}")

with open('test_retorno_postman.json', 'w', encoding='utf-8') as f:
    f.write(json.dumps(results, indent=2, ensure_ascii=False, default=str))
print("\nSaved to test_retorno_postman.json")
