import json, os, ssl, urllib.request

env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip().replace('\r','')
            if not line or line.startswith('#'): continue
            if '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

base = os.environ.get('OAZ_BASE_URL','').rstrip('/')
ctx = ssl.create_default_context()

# Auth
body = json.dumps({'chave':1,'usuario':os.environ.get('OAZ_USUARIO',''),'senha':os.environ.get('OAZ_SENHA','')}).encode()
req = urllib.request.Request(f'{base}/autenticacao', data=body, method='POST', headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
    token = json.loads(r.read().decode())['retorno']['token']
print(f'Token OK: {token[:30]}...')

# Retorno - buscar S27TH033
payload = {
    "pagina": 1,
    "campos": {"campos": ["modelo.id"]},
    "filtros": [{"campo": "modelo.ds_referencia", "operador": "%like%", "valor": "S27TH033"}]
}
body2 = json.dumps(payload).encode()
req2 = urllib.request.Request(f'{base}/retorno/modelo', data=body2, method='POST',
    headers={'Content-Type':'application/json','Authorization':f'Bearer {token}'})
with urllib.request.urlopen(req2, timeout=30, context=ctx) as r2:
    result = json.loads(r2.read().decode())
    print(json.dumps(result, indent=2, ensure_ascii=False))
