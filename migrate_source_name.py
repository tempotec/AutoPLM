"""
Migration: Add source_name column to oaz_value_map
===================================================
Adds the source_name column to track which XLSX file each WSID mapping came from.
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv('.env.local')


def run():
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        print('ERROR: DATABASE_URL not set')
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        cur.execute(
            'ALTER TABLE oaz_value_map ADD COLUMN source_name VARCHAR(255)'
        )
        print('  + Added column oaz_value_map.source_name')
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
        conn.autocommit = True
        print('  ~ Column oaz_value_map.source_name already exists')

    cur.close()
    conn.close()
    print('\nMigração concluída!')


if __name__ == '__main__':
    print('=== Migrate: oaz_value_map.source_name ===')
    run()
