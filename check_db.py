import os
from dotenv import load_dotenv
load_dotenv('.env.local')
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

# List all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = cur.fetchall()
print(f"=== {len(tables)} tables in public schema ===")
for t in tables:
    print(f"  {t[0]}")

# Check oaz_value_map
print()
cur.execute("SELECT field_key, COUNT(*) FROM oaz_value_map GROUP BY field_key ORDER BY field_key")
rows = cur.fetchall()
print("=== oaz_value_map counts ===")
for r in rows:
    print(f"  {r[0]}: {r[1]}")

cur.execute("SELECT COUNT(*) FROM oaz_value_map")
print(f"TOTAL: {cur.fetchone()[0]}")

# Show connection info
cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port()")
info = cur.fetchone()
print(f"\nConnected to: db={info[0]} server={info[1]}:{info[2]}")

cur.close()
conn.close()
