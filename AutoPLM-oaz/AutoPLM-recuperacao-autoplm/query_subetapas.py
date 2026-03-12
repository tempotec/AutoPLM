import json, os, ssl, urllib.request, urllib.error
from dotenv import load_dotenv
load_dotenv('.env')
from app.integrations.fluxogama.token_manager import _authenticate
from app import create_app

app = create_app()
with app.app_context():
    token = _authenticate()
    base_url = os.environ.get('OAZ_BASE_URL', '').rstrip('/')
    sslctx = ssl.create_default_context()
    url = f"{base_url}/remessa/modelo"

    # Test different subetapa values - use a safe test referencia
    sub_values = ["5", "6", "9", "10", "11", "14", "17", "20", "31", "32", "33", "34", "51", "54", "55", "89", "93", "94"]
    results = {}
    
    for sv in sub_values:
        payload = [{
            "referencia": f"TESTE-SUBETAPA-{sv}",
            "colecao": "61",
            "ws_id": f"test_sub_{sv}",
            "codigo": f"test_sub_{sv}",
            "sistema_criar_modelo": 1,
            "subetapa": sv,
            "uno.12": "TESTE",
        }]
        body = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=body, method='POST', headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Authorization': f'Bearer {token}',
        })
        try:
            with urllib.request.urlopen(req, timeout=15, context=sslctx) as resp:
                r = json.loads(resp.read().decode())
                results[sv] = "VALID - " + json.dumps(r, ensure_ascii=False)[:150]
        except urllib.error.HTTPError as e:
            err = ''
            try: err = e.read().decode()[:300]
            except: pass
            if 'Subetapa' in err and 'encontrada' in err:
                results[sv] = "INVALID_SUBETAPA"
            else:
                results[sv] = f"OTHER_ERROR_{e.code}: {err[:100]}"
        except Exception as e:
            results[sv] = f"EXCEPTION: {e}"

    with open('subetapa_test_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    # Print summary
    valid = [k for k, v in results.items() if 'VALID -' in v]
    invalid = [k for k, v in results.items() if v == 'INVALID_SUBETAPA']
    other = [k for k, v in results.items() if k not in valid and k not in invalid]
    
    summary = f"VALID: {valid}\nINVALID: {invalid}\nOTHER: {other}"
    with open('subetapa_summary.txt', 'w') as f:
        f.write(summary)
