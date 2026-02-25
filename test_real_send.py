"""Check JWT expiry and do the first real send."""
import os
import json
import base64
from datetime import datetime

os.environ['APP_ENV'] = 'development'

# 1) Check JWT expiry
token = os.environ.get('FLUXOGAMA_CHAVE', '')
if not token:
    from dotenv import load_dotenv
    load_dotenv('.env.local')
    token = os.environ.get('FLUXOGAMA_CHAVE', '')

if token:
    parts = token.split('.')
    if len(parts) >= 2:
        payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
        try:
            payload_data = json.loads(base64.b64decode(payload_b64))
            iat = datetime.utcfromtimestamp(payload_data.get('iat', 0))
            exp = datetime.utcfromtimestamp(payload_data.get('exp', 0))
            now = datetime.utcnow()
            expired = now.timestamp() > payload_data.get('exp', 0)
            print("=== JWT CHECK ===")
            print(f"  Subject: {payload_data.get('sub')}")
            print(f"  Issuer:  {payload_data.get('iss')}")
            print(f"  Issued:  {iat}")
            print(f"  Expires: {exp}")
            print(f"  Now:     {now}")
            print(f"  Expired: {expired}")
            if expired:
                print("\n⚠️  TOKEN EXPIRADO — o envio real vai falhar com 401/403.")
                print("  Precisa renovar FLUXOGAMA_CHAVE no .env.local")
        except Exception as e:
            print(f"Erro ao decodar JWT: {e}")
else:
    print("FLUXOGAMA_CHAVE não encontrada")

print()

# 2) Do the real send
from app import create_app
from app.extensions import db
from app.models import User, FichaTecnicaItem

app = create_app()

with app.app_context():
    with app.test_client() as client:
        with client.session_transaction() as sess:
            user = User.query.first()
            sess['user_id'] = user.id

        ficha_id = 2
        item_id = 8

        print("=" * 60)
        print(f" STEP 1: Preview (GET payload) — ficha={ficha_id} item={item_id}")
        print("=" * 60)
        r1 = client.get(f'/api/fluxogama/payload/ficha/{ficha_id}/item/{item_id}')
        d1 = r1.get_json()
        print(f"Status: {r1.status_code}")
        print(f"Valid: {d1.get('valid')}")
        print(f"Errors: {d1.get('errors')}")
        if not d1.get('valid'):
            print("❌ Item not valid — cannot proceed with real send")
            exit(1)
        print("✅ Preview OK\n")

        print("=" * 60)
        print(f" STEP 2: Dry-run (POST ?dry_run=1)")
        print("=" * 60)
        r2 = client.post(f'/api/fluxogama/send/ficha/{ficha_id}/item/{item_id}?dry_run=1')
        d2 = r2.get_json()
        print(f"Status: {r2.status_code}")
        print(f"Fluxogama status: {d2.get('fluxogama_status')}")
        if r2.status_code != 200:
            print(f"❌ Dry-run failed: {d2.get('error')}")
            exit(1)
        print("✅ Dry-run OK\n")

        print("=" * 60)
        print(f" STEP 3: REAL SEND (POST without dry_run)")
        print("=" * 60)
        r3 = client.post(f'/api/fluxogama/send/ficha/{ficha_id}/item/{item_id}')
        d3 = r3.get_json()
        print(f"Status: {r3.status_code}")
        print(f"\nFull response:")
        print(json.dumps(d3, indent=2, ensure_ascii=False))

        if d3.get('fluxogama_status') == 'success' or d3.get('sent'):
            print("\n✅ REAL SEND SUCCEEDED")
        else:
            print(f"\n❌ REAL SEND RESULT: {d3.get('fluxogama_status')}")
            print(f"   Error: {d3.get('fluxogama_error')}")

        print()
        print("=" * 60)
        print(f" STEP 4: Dedup post-send (repeat without force)")
        print("=" * 60)
        r4 = client.post(f'/api/fluxogama/send/ficha/{ficha_id}/item/{item_id}')
        d4 = r4.get_json()
        print(f"Status: {r4.status_code}")
        if r4.status_code == 409:
            print("✅ Dedup OK — returned 409 as expected")
        else:
            print(f"⚠️ Expected 409, got {r4.status_code}")
        print(json.dumps(d4, indent=2, ensure_ascii=False))

        print()
        print("=" * 60)
        print(f" STEP 5: Force resend (with force=1)")
        print("=" * 60)
        r5 = client.post(f'/api/fluxogama/send/ficha/{ficha_id}/item/{item_id}?force=1')
        d5 = r5.get_json()
        print(f"Status: {r5.status_code}")
        print(json.dumps(d5, indent=2, ensure_ascii=False))
        if r5.status_code == 200:
            print("✅ Force resend OK")
        else:
            print(f"⚠️ Expected 200, got {r5.status_code}")

        print()
        print("=" * 60)
        print(" SUMMARY")
        print("=" * 60)
        # Check DB state
        item = FichaTecnicaItem.query.get(item_id)
        print(f"  Item {item_id} final DB state:")
        print(f"    fluxogama_status:  {item.fluxogama_status}")
        print(f"    fluxogama_sent_at: {item.fluxogama_sent_at}")
        print(f"    fluxogama_response (first 200 chars): {(item.fluxogama_response or '')[:200]}")
