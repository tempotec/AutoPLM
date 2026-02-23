"""
Migration: Add OAZ integration columns and table
=================================================
Adds oaz_* tracking columns to ficha_tecnica_item
and creates the oaz_value_map table for WSID mappings.
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv('.env.local')


def get_connection():
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        print('ERROR: DATABASE_URL not set')
        sys.exit(1)
    return psycopg2.connect(db_url)


def run_migration():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # ── Add OAZ tracking columns to ficha_tecnica_item ─────────────────
    oaz_columns = [
        ('oaz_status',        'VARCHAR(50)'),
        ('oaz_pushed_at',     'TIMESTAMP'),
        ('oaz_remote_id',     'VARCHAR(255)'),
        ('oaz_last_error',    'TEXT'),
        ('oaz_payload_hash',  'VARCHAR(64)'),
        ('oaz_last_response', 'TEXT'),
    ]

    for col_name, col_type in oaz_columns:
        try:
            cur.execute(
                f'ALTER TABLE ficha_tecnica_item ADD COLUMN {col_name} {col_type}'
            )
            print(f'  + Added column ficha_tecnica_item.{col_name}')
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()
            conn.autocommit = True
            print(f'  ~ Column ficha_tecnica_item.{col_name} already exists')

    # ── Create oaz_value_map table ─────────────────────────────────────
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS oaz_value_map (
                id SERIAL PRIMARY KEY,
                field_key VARCHAR(50) NOT NULL,
                text_value VARCHAR(255) NOT NULL,
                text_norm VARCHAR(255) NOT NULL,
                wsid_value VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT uq_oaz_map_field_text UNIQUE (field_key, text_norm)
            )
        ''')
        print('  + Created table oaz_value_map')
    except Exception as e:
        print(f'  ~ Table oaz_value_map: {e}')
        conn.rollback()
        conn.autocommit = True

    # Index
    try:
        cur.execute(
            'CREATE INDEX IF NOT EXISTS ix_oaz_map_field_key ON oaz_value_map (field_key)'
        )
        print('  + Created index ix_oaz_map_field_key')
    except Exception as e:
        print(f'  ~ Index: {e}')

    cur.close()
    conn.close()
    print('\nMigração OAZ concluída com sucesso!')


if __name__ == '__main__':
    print('=== Migração OAZ ===')
    run_migration()
