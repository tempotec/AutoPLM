"""Add missing columns to ficha_tecnica_item table."""
from app import create_app
from app.extensions import db
from sqlalchemy import text, inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    existing = {c['name'] for c in inspector.get_columns('ficha_tecnica_item')}
    
    missing = [
        ("colecao", "VARCHAR(255)"),
        ("fluxogama_status", "VARCHAR(50)"),
        ("fluxogama_sent_at", "TIMESTAMP"),
        ("fluxogama_response", "TEXT"),
    ]
    
    for col_name, col_type in missing:
        if col_name in existing:
            print(f"  ~ {col_name} already exists")
        else:
            db.session.execute(text(f"ALTER TABLE ficha_tecnica_item ADD COLUMN {col_name} {col_type}"))
            print(f"  + Added {col_name} ({col_type})")
    
    db.session.commit()
    print("\nDone!")
