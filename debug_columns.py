"""Quick test of just the preview endpoint to see the full error."""
import json, traceback
from app import create_app
from app.extensions import db
from app.models import User, FichaTecnica, FichaTecnicaItem

app = create_app()

with app.app_context():
    client = app.test_client()
    
    # Force session
    with client.session_transaction() as sess:
        user = User.query.first()
        if user:
            sess['user_id'] = user.id
            sess['is_admin'] = getattr(user, 'is_admin', False)
        else:
            sess['user_id'] = 1
            sess['is_admin'] = True
    
    # Find ficha
    ficha = FichaTecnica.query.first()
    if not ficha:
        print("No fichas found")
        exit(1)
    
    print(f"Testing ficha ID={ficha.id}")
    
    # Check what columns actually exist
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    cols = [c['name'] for c in inspector.get_columns('ficha_tecnica_item')]
    print(f"\nDB columns ({len(cols)}):")
    for c in sorted(cols):
        print(f"  {c}")
    
    # Check model columns
    model_cols = [c.key for c in FichaTecnicaItem.__table__.columns]
    print(f"\nModel columns ({len(model_cols)}):")
    for c in sorted(model_cols):
        print(f"  {c}")
    
    # Find missing
    missing = set(model_cols) - set(cols)
    if missing:
        print(f"\n*** MISSING columns (in model but not DB): {missing}")
    else:
        print("\n*** All model columns exist in DB")
    
    extra = set(cols) - set(model_cols)
    if extra:
        print(f"*** Extra DB columns (in DB but not model): {extra}")
