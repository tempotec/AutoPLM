"""Verify that sent_at stays None on error (token expired = 401)."""
import os, json
os.environ['APP_ENV'] = 'development'
from app import create_app
from app.extensions import db
from app.models import User, FichaTecnicaItem

app = create_app()
with app.app_context():
    with app.test_client() as client:
        with client.session_transaction() as sess:
            user = User.query.first()
            sess['user_id'] = user.id

        # Real send (will get 401 since token expired)
        r = client.post('/api/fluxogama/send/ficha/2/item/8')
        d = r.get_json()
        print(f"Status: {r.status_code}")
        print(f"fluxogama_status: {d.get('fluxogama_status')}")
        print(f"fluxogama_error: {d.get('fluxogama_error')}")

    # Check DB state
    item = FichaTecnicaItem.query.get(8)
    print(f"\nDB state:")
    print(f"  fluxogama_status:  {item.fluxogama_status}")
    print(f"  fluxogama_sent_at: {item.fluxogama_sent_at}")
    print(f"  fluxogama_response: {(item.fluxogama_response or '')[:200]}")

    if item.fluxogama_status == 'error' and item.fluxogama_sent_at is None:
        print("\n✅ PASS: sent_at is None on error")
    elif item.fluxogama_status == 'error' and item.fluxogama_sent_at is not None:
        print("\n❌ FAIL: sent_at should be None on error")
    else:
        print(f"\n⚠️ Unexpected status: {item.fluxogama_status}")

    # Reset for next test
    item.fluxogama_status = None
    item.fluxogama_sent_at = None
    item.fluxogama_response = None
    db.session.commit()
    print("Item 8 reset to clean state.")
