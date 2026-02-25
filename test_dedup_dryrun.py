"""
Test dedup-in-dry-run behavior.
Marks item 8 as 'sent', verifies:
1. Single dry-run returns 409
2. Batch dry-run shows skipped_count=1
3. force=1 bypasses dedup
"""
import os
import json

os.environ['APP_ENV'] = 'development'
from app import create_app
from app.extensions import db
from app.models import User, FichaTecnicaItem
from datetime import datetime

app = create_app()

with app.app_context():
    # Mark item 8 as 'sent' to test dedup-in-dry-run
    item = FichaTecnicaItem.query.get(8)
    item.fluxogama_status = 'sent'
    item.fluxogama_sent_at = datetime.utcnow()
    db.session.commit()
    print(f'Item 8 marked as sent at {item.fluxogama_sent_at}')

    with app.test_client() as client:
        with client.session_transaction() as sess:
            user = User.query.first()
            sess['user_id'] = user.id

        # Test 1: single item dry-run → should be 409 (dedup fires)
        r1 = client.post('/api/fluxogama/send/ficha/2/item/8?dry_run=1')
        print(f'\n--- Test 1: Single dry-run (item already sent) ---')
        print(f'Status: {r1.status_code}')
        d1 = r1.get_json()
        print(json.dumps(d1, indent=2, ensure_ascii=False))
        assert r1.status_code == 409, f'Expected 409, got {r1.status_code}'
        print('✅ PASS: dedup fires on dry-run (409)')

        # Test 2: batch dry-run with item 8 (sent) + item 9 (pending) + item 10 (no colecao)
        r2 = client.post(
            '/api/fluxogama/send-batch?dry_run=1',
            data=json.dumps({'ficha_id': 2, 'item_ids': [8, 9, 10]}),
            content_type='application/json',
        )
        print(f'\n--- Test 2: Batch dry-run ---')
        print(f'Status: {r2.status_code}')
        d2 = r2.get_json()
        print(json.dumps(d2, indent=2, ensure_ascii=False))
        sk = d2.get('skipped_count', -1)
        sc = d2.get('success_count', -1)
        ec = d2.get('error_count', -1)
        assert sk == 1, f'Expected skipped_count=1, got {sk}'
        assert sc == 1, f'Expected success_count=1, got {sc}'
        assert ec == 1, f'Expected error_count=1, got {ec}'
        print('✅ PASS: batch dry-run shows skipped=1, success=1, error=1')

        # Test 3: single item with force=1 should bypass dedup
        r3 = client.post('/api/fluxogama/send/ficha/2/item/8?dry_run=1&force=1')
        print(f'\n--- Test 3: Single dry-run with force=1 ---')
        print(f'Status: {r3.status_code}')
        assert r3.status_code == 200, f'Expected 200, got {r3.status_code}'
        print('✅ PASS: force=1 bypasses dedup')

    # Reset item 8 back to None for clean state
    item.fluxogama_status = None
    item.fluxogama_sent_at = None
    db.session.commit()
    print('\nItem 8 reset to clean state.')
    print('\n=== ALL DEDUP-IN-DRY-RUN TESTS PASSED ===')
