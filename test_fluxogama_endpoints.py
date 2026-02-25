"""
End-to-end test for Fluxogama integration endpoints.
Uses Flask test client with forced session to bypass login.
"""
import json
import sys
from app import create_app
from app.extensions import db
from app.models import User, FichaTecnica, FichaTecnicaItem

app = create_app()
client = app.test_client()


# ---------- Helper ----------
def api(method, path, json_data=None):
    """Make authenticated request via test client."""
    with client.session_transaction() as sess:
        user = None
        with app.app_context():
            user = User.query.first()
        if user:
            sess['user_id'] = user.id
            sess['is_admin'] = getattr(user, 'is_admin', False)
        else:
            sess['user_id'] = 1
            sess['is_admin'] = True

    if method == 'GET':
        resp = client.get(path, content_type='application/json')
    elif method == 'POST':
        resp = client.post(
            path,
            data=json.dumps(json_data) if json_data else None,
            content_type='application/json',
        )
    else:
        raise ValueError(f"Unknown method: {method}")

    try:
        data = resp.get_json()
    except Exception:
        data = {'_raw': resp.data.decode()[:1000]}

    return resp.status_code, data


# ---------- Find test data ----------
print("=" * 60)
print(" Fluxogama Integration - E2E Validation")
print("=" * 60)

with app.app_context():
    fichas = FichaTecnica.query.all()
    print(f"\nTotal fichas no DB: {len(fichas)}")
    for f in fichas:
        item_count = FichaTecnicaItem.query.filter_by(ficha_id=f.id).count()
        print(f"  Ficha ID={f.id} | PI={f.number_pi_order} | source={f.source_filename} | items={item_count}")

    # Pick a ficha with items
    test_ficha = None
    test_items = []
    for f in fichas:
        items = FichaTecnicaItem.query.filter_by(ficha_id=f.id).limit(5).all()
        if items:
            test_ficha = f
            test_items = items
            break

    if not test_ficha:
        print("\n❌ No fichas with items found in DB. Cannot proceed.")
        sys.exit(1)

    ficha_id = test_ficha.id
    item_id = test_items[0].id
    print(f"\nUsing: ficha_id={ficha_id}, item_id={item_id}")
    print(f"  Item ref: {test_items[0].item_no_ref_supplier}")
    print(f"  Item oaz_ref: {test_items[0].oaz_reference}")
    print(f"  Item nome: {test_items[0].nome_desc_produto}")
    print(f"  Item colecao: {test_items[0].colecao}")
    print(f"  Item grupo: {test_items[0].grupo}")
    print(f"  Item sub_grupo: {test_items[0].sub_grupo}")
    print(f"  Item cor_sistema: {test_items[0].cor_sistema}")
    print(f"  Item fluxogama_status: {test_items[0].fluxogama_status}")
    print(f"  Item raw_row present: {bool(test_items[0].raw_row)}")

# ---------- STEP 1: Preview ----------
print(f"\n{'=' * 60}")
print(f" STEP 1: GET /api/fluxogama/payload/ficha/{ficha_id}/item/{item_id}")
print("=" * 60)

status, data = api('GET', f'/api/fluxogama/payload/ficha/{ficha_id}/item/{item_id}')
print(f"Status: {status}")
print(f"\nFull JSON response:")
print(json.dumps(data, indent=2, ensure_ascii=False))

step1_ok = status == 200 and 'payload' in data
print(f"\nResult: {'✅ PASS' if step1_ok else '❌ FAIL'}")

if data.get('errors'):
    print(f"\n⚠️  Errors ({len(data['errors'])}):")
    for e in data['errors']:
        print(f"  - {e}")

if data.get('warnings'):
    print(f"\n⚠️  Warnings ({len(data['warnings'])}):")
    for w in data['warnings']:
        print(f"  - {w}")

# ---------- STEP 2: Dry-Run Send ----------
print(f"\n{'=' * 60}")
print(f" STEP 2: POST /api/fluxogama/send/ficha/{ficha_id}/item/{item_id}?dry_run=1")
print("=" * 60)

status2, data2 = api('POST', f'/api/fluxogama/send/ficha/{ficha_id}/item/{item_id}?dry_run=1')
print(f"Status: {status2}")
print(f"\nFull JSON response:")
print(json.dumps(data2, indent=2, ensure_ascii=False))

step2_ok = status2 in (200, 422, 409)
print(f"\nResult: {'✅ PASS' if step2_ok else '❌ FAIL'} (status={status2})")

# ---------- STEP 3: Batch dry-run (first 3 items) ----------
if len(test_items) >= 2:
    batch_ids = [it.id for it in test_items[:3]]
    print(f"\n{'=' * 60}")
    print(f" STEP 3: POST /api/fluxogama/send-batch?dry_run=1")
    print(f" Items: {batch_ids}")
    print("=" * 60)

    status3, data3 = api('POST', '/api/fluxogama/send-batch?dry_run=1', {
        'ficha_id': ficha_id,
        'item_ids': batch_ids,
    })
    print(f"Status: {status3}")
    print(f"\nFull JSON response:")
    print(json.dumps(data3, indent=2, ensure_ascii=False))

    step3_ok = status3 == 200
    print(f"\nResult: {'✅ PASS' if step3_ok else '❌ FAIL'}")
else:
    step3_ok = True
    print("\n[SKIP] Not enough items to test batch")

# ---------- STEP 4: Test multiple items preview (scan for common errors) ----------
print(f"\n{'=' * 60}")
print(f" STEP 4: Preview scan of ALL items (ficha {ficha_id})")
print("=" * 60)

with app.app_context():
    all_items = FichaTecnicaItem.query.filter_by(ficha_id=ficha_id).all()

error_summary = {}
warning_summary = {}
valid_count = 0
invalid_count = 0

for it in all_items:
    s, d = api('GET', f'/api/fluxogama/payload/ficha/{ficha_id}/item/{it.id}')
    if s == 200:
        if d.get('valid'):
            valid_count += 1
        else:
            invalid_count += 1
        for e in d.get('errors', []):
            error_summary[e] = error_summary.get(e, 0) + 1
        for w in d.get('warnings', []):
            warning_summary[w] = warning_summary.get(w, 0) + 1

print(f"Total items scanned: {len(all_items)}")
print(f"  ✅ Valid: {valid_count}")
print(f"  ❌ Invalid: {invalid_count}")

if error_summary:
    print(f"\nTop errors (by frequency):")
    for e, count in sorted(error_summary.items(), key=lambda x: -x[1]):
        print(f"  [{count}x] {e}")

if warning_summary:
    print(f"\nTop warnings (by frequency):")
    for w, count in sorted(warning_summary.items(), key=lambda x: -x[1]):
        print(f"  [{count}x] {w}")

# ---------- SUMMARY ----------
print(f"\n{'=' * 60}")
print(" SUMMARY")
print("=" * 60)
results = {
    "1. Preview": step1_ok,
    "2. Dry-Run Send": step2_ok,
    "3. Batch Dry-Run": step3_ok,
}
for name, ok in results.items():
    print(f"  {'✅' if ok else '❌'} {name}")

total = sum(results.values())
print(f"\n  {total}/{len(results)} passed")
