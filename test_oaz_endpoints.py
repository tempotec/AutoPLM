"""
End-to-end test for OAZ integration endpoints.
Uses Flask test client with forced session to bypass login.
"""
import json, sys
from app import create_app
from app.extensions import db
from app.models import User

app = create_app()
client = app.test_client()

# ---------- Helper ----------
def api(method, path, json_data=None):
    """Make authenticated request via test client."""
    with client.session_transaction() as sess:
        # Force a valid user session
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
        resp = client.post(path, data=json.dumps(json_data) if json_data else None,
                          content_type='application/json')
    elif method == 'DELETE':
        resp = client.delete(path, content_type='application/json')
    else:
        raise ValueError(f"Unknown method: {method}")

    try:
        data = resp.get_json()
    except Exception:
        data = {'_raw': resp.data.decode()[:500]}

    return resp.status_code, data

# ---------- Tests ----------
print("=" * 60)
print(" OAZ Integration - End-to-End Validation")
print("=" * 60)

# 1) Health Check
print("\n--- STEP 1: GET /api/oaz/health ---")
status, data = api('GET', '/api/oaz/health')
print(f"  Status: {status}")
print(f"  Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
step1_ok = data.get('success') is True or status == 200
print(f"  Result: {'PASS' if step1_ok else 'CHECK' } (success={data.get('success')})")

# 2) Mapping WSID
print("\n--- STEP 2: POST /api/oaz/mapping ---")
mappings_payload = {
    "mappings": [
        {"field_key": "uno.10", "text_value": "ACESSÓRIOS", "wsid_value": "9283"},
        {"field_key": "uno.11", "text_value": "LENÇO", "wsid_value": "9284"},
        {"field_key": "uno.12", "text_value": "LENÇO ESTAMPADO", "wsid_value": "9285"},
        {"field_key": "uno.24", "text_value": "POLYESTER", "wsid_value": "9286"},
    ]
}
status, data = api('POST', '/api/oaz/mapping', mappings_payload)
print(f"  Status: {status}")
print(f"  Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
step2_ok = data.get('success') is True
print(f"  Result: {'PASS' if step2_ok else 'FAIL'}")

# 2b) List Mappings
print("\n--- STEP 2b: GET /api/oaz/mapping ---")
status, data = api('GET', '/api/oaz/mapping')
print(f"  Status: {status}")
print(f"  Total mappings: {data.get('total', 0)}")
if data.get('mappings'):
    for m in data['mappings'][:5]:
        print(f"    {m.get('field_key')} | {m.get('text_value')} -> {m.get('wsid_value')}")
step2b_ok = data.get('success') is True and data.get('total', 0) > 0
print(f"  Result: {'PASS' if step2b_ok else 'FAIL'}")

# 3) Preview (find a ficha first)
print("\n--- STEP 3: Finding a ficha to test ---")
from app.models import FichaTecnica, FichaTecnicaItem
with app.app_context():
    ficha = FichaTecnica.query.first()
    if ficha:
        item_count = FichaTecnicaItem.query.filter_by(ficha_id=ficha.id).count()
        print(f"  Found ficha ID={ficha.id}, source_filename={getattr(ficha, 'source_filename', 'N/A')}, items={item_count}")
    else:
        print("  No fichas found in database")
        ficha = None

if ficha:
    print(f"\n--- STEP 3b: GET /api/fichas/{ficha.id}/oaz/preview ---")
    status, data = api('GET', f'/api/fichas/{ficha.id}/oaz/preview')
    print(f"  Status: {status}")
    if data.get('success'):
        print(f"  Total items: {data.get('total_items')}")
        print(f"  Total errors: {data.get('total_errors')}")
        print(f"  Total warnings: {data.get('total_warnings')}")
        print(f"  Ready to push: {data.get('ready_to_push')}")
        # Show first 2 items
        for item in (data.get('items') or [])[:2]:
            print(f"\n  Item #{item.get('item_id')} (ref={item.get('item_ref')}):")
            print(f"    Valid: {item.get('valid')}")
            print(f"    Errors: {item.get('errors')}")
            print(f"    Warnings: {item.get('warnings')}")
            print(f"    Fallbacks: {item.get('fallbacks')}")
            payload = item.get('payload', {})
            for k, v in sorted(payload.items()):
                print(f"    {k}: {v}")
    else:
        print(f"  Error: {data.get('error')}")
    step3_ok = status == 200
    print(f"  Result: {'PASS' if step3_ok else 'FAIL'}")

    # 4) Dry Run Push
    print(f"\n--- STEP 4: POST /api/fichas/{ficha.id}/oaz/push (dry_run) ---")
    status, data = api('POST', f'/api/fichas/{ficha.id}/oaz/push', {"dry_run": True})
    print(f"  Status: {status}")
    if data.get('success'):
        summary = data.get('summary', {})
        print(f"  Summary: total={summary.get('total')}, dry_run={summary.get('dry_run')}, failed={summary.get('failed')}")
        # Show first 2 items
        for item in (data.get('items') or [])[:2]:
            print(f"    Item #{item.get('item_id')}: {item.get('status')}")
            if item.get('errors'):
                print(f"      Errors: {item.get('errors')}")
    else:
        print(f"  Error: {data.get('error')}")
    step4_ok = status == 200
    print(f"  Result: {'PASS' if step4_ok else 'FAIL'}")

    # 5) Status
    print(f"\n--- STEP 5: GET /api/fichas/{ficha.id}/oaz/status ---")
    status, data = api('GET', f'/api/fichas/{ficha.id}/oaz/status')
    print(f"  Status: {status}")
    if data.get('success'):
        print(f"  Total: {data.get('total')}")
        print(f"  Counts: {data.get('counts')}")
    else:
        print(f"  Error: {data.get('error')}")
    step5_ok = status == 200
    print(f"  Result: {'PASS' if step5_ok else 'FAIL'}")
else:
    step3_ok = step4_ok = step5_ok = False
    print("  SKIPPED (no fichas)")

# Summary
print("\n" + "=" * 60)
print(" SUMMARY")
print("=" * 60)
results = {
    "1. Health": step1_ok,
    "2. Mapping POST": step2_ok,
    "2b. Mapping GET": step2b_ok,
}
if ficha:
    results.update({
        "3. Preview": step3_ok,
        "4. Dry Run Push": step4_ok,
        "5. Status": step5_ok,
    })

for name, ok in results.items():
    print(f"  {'✅' if ok else '❌'} {name}")

total = sum(results.values())
print(f"\n  {total}/{len(results)} passed")
