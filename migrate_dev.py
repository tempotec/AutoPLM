"""
Migrate schema to Neon development branch.
Creates all tables + unique index + source_name column.
"""
import os
import sys

# Override DATABASE_URL to point to the development branch
DEV_URL = "postgresql://neondb_owner:npg_mNdSqh3Z8fgB@ep-cold-sea-ad0fxv9k.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"
os.environ['DATABASE_URL'] = DEV_URL

# Now init Flask app (which reads DATABASE_URL)
sys.path.insert(0, '.')
from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    print(f"Connecting to: {DEV_URL[:60]}...")

    # Create all tables from models
    db.create_all()
    print("✅ All tables created via db.create_all()")

    # Add source_name column if missing
    from sqlalchemy import text
    try:
        db.session.execute(text("ALTER TABLE oaz_value_map ADD COLUMN IF NOT EXISTS source_name VARCHAR(255)"))
        db.session.commit()
        print("✅ source_name column ensured")
    except Exception as e:
        db.session.rollback()
        print(f"⚠️  source_name: {e}")

    # Create unique index
    try:
        db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_oaz_map_field_text ON oaz_value_map (field_key, text_norm)"))
        db.session.commit()
        print("✅ Unique index uix_oaz_map_field_text created")
    except Exception as e:
        db.session.rollback()
        print(f"⚠️  Index: {e}")

    # Verify
    result = db.session.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
    tables = [r[0] for r in result.fetchall()]
    print(f"\n📋 {len(tables)} tables in dev branch:")
    for t in tables:
        print(f"   {t}")

    print("\n✅ Migration complete!")
