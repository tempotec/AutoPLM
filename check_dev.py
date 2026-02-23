"""Check and create tables on the Neon development branch."""
import psycopg2

DEV_URL = "postgresql://neondb_owner:npg_mNdSqh3Z8fgB@ep-cold-sea-ad0fxv9k.c-2.us-east-1.aws.neon.tech/neondb?sslmode=require"

print(f"Connecting to dev branch...")
conn = psycopg2.connect(DEV_URL)
cur = conn.cursor()

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print(f"\n{len(tables)} tables found:")
for t in tables:
    print(f"  {t}")

if 'oaz_value_map' in tables:
    cur.execute("SELECT COUNT(*) FROM oaz_value_map")
    print(f"\noaz_value_map rows: {cur.fetchone()[0]}")

cur.close()
conn.close()
