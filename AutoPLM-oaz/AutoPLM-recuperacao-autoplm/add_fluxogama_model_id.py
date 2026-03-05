"""
Migration: Add fluxogama_model_id column and set ID 11788 for S27TH033
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip().replace('\r', '')
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # 1. Add column if not exists
    print("1. Adding fluxogama_model_id column...")
    try:
        conn.execute(text(
            "ALTER TABLE specification ADD COLUMN IF NOT EXISTS fluxogama_model_id INTEGER"
        ))
        conn.commit()
        print("   OK (column added or already exists)")
    except Exception as e:
        print(f"   Note: {e}")
        conn.rollback()

    # 2. Set fluxogama_model_id = 11788 for ref_souq = 'S27TH033'
    print("\n2. Setting fluxogama_model_id=11788 for ref_souq='S27TH033'...")
    result = conn.execute(text(
        "UPDATE specification SET fluxogama_model_id = 11788 WHERE ref_souq = 'S27TH033'"
    ))
    conn.commit()
    rows_updated = result.rowcount
    print(f"   Updated {rows_updated} row(s)")

    # 3. Verify
    print("\n3. Verifying...")
    rows = conn.execute(text(
        "SELECT id, ref_souq, fluxogama_model_id, description "
        "FROM specification WHERE ref_souq = 'S27TH033'"
    )).fetchall()
    
    if rows:
        for row in rows:
            print(f"   spec_id={row[0]} | ref_souq={row[1]} | fluxogama_model_id={row[2]} | desc={str(row[3])[:60]}")
    else:
        print("   WARNING: No specs found with ref_souq='S27TH033'")
        # Show available refs
        sample = conn.execute(text(
            "SELECT id, ref_souq, fluxogama_model_id FROM specification ORDER BY id DESC LIMIT 10"
        )).fetchall()
        print("   Latest specs:")
        for row in sample:
            print(f"     id={row[0]} | ref_souq={row[1]} | fluxogama_model_id={row[2]}")

print("\nDone!")
