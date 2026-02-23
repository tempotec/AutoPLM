"""Fix missing raw_row column in ficha_tecnica_item table."""
from app import create_app
from app.extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    result = db.session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'ficha_tecnica_item' AND column_name = 'raw_row'"
    ))
    exists = result.fetchone()
    if exists:
        print('raw_row column already exists')
    else:
        print('raw_row column MISSING - adding it now')
        db.session.execute(text('ALTER TABLE ficha_tecnica_item ADD COLUMN raw_row TEXT'))
        db.session.commit()
        print('raw_row column ADDED successfully')
