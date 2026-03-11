"""
Migration: Sync production database schema with development
============================================================
Adds missing columns to ficha_tecnica_item, specification, and oaz_value_map
tables in the production database.

Usage:
    python migrate_prod_sync.py          # uses .env.prod
    python migrate_prod_sync.py --dev    # uses .env.local (for testing)
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Choose env file based on CLI arg
if '--dev' in sys.argv:
    load_dotenv('.env.local')
    print('Using .env.local (development)')
else:
    load_dotenv('.env.prod')
    print('Using .env.prod (production)')


def get_connection():
    db_url = os.environ.get('DATABASE_URL', '')
    if not db_url:
        print('ERROR: DATABASE_URL not set')
        sys.exit(1)
    return psycopg2.connect(db_url)


def add_column(cur, conn, table, col_name, col_type):
    try:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type}')
        print(f'  + Added {table}.{col_name}')
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
        conn.autocommit = True
        print(f'  ~ {table}.{col_name} already exists')


def run_migration():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # ── 1. ficha_tecnica_item: 14 missing columns ──────────────────────
    print('\n=== ficha_tecnica_item ===')
    fti_columns = [
        ('colecao',              'VARCHAR(100)'),
        ('fluxogama_response',   'TEXT'),
        ('fluxogama_sent_at',    'TIMESTAMP'),
        ('fluxogama_status',     'VARCHAR(50)'),
        ('mkp_5_5',              'DOUBLE PRECISION'),
        ('mkup_7',               'DOUBLE PRECISION'),
        ('oaz_last_error',       'TEXT'),
        ('oaz_last_response',    'TEXT'),
        ('oaz_payload_hash',     'VARCHAR(64)'),
        ('oaz_pushed_at',        'TIMESTAMP'),
        ('oaz_remote_id',        'VARCHAR(255)'),
        ('oaz_status',           'VARCHAR(50)'),
        ('price_negotiation',    'VARCHAR(100)'),
        ('wholesale_sample_qty', 'DOUBLE PRECISION'),
    ]

    for col_name, col_type in fti_columns:
        add_column(cur, conn, 'ficha_tecnica_item', col_name, col_type)

    # ── 2. specification: 1 missing column ─────────────────────────────
    print('\n=== specification ===')
    add_column(cur, conn, 'specification', 'fluxogama_model_id', 'INTEGER')

    # ── 3. oaz_value_map: 1 missing column ─────────────────────────────
    print('\n=== oaz_value_map ===')
    add_column(cur, conn, 'oaz_value_map', 'tenant_id', 'INTEGER')

    cur.close()
    conn.close()
    print('\nMigração concluída com sucesso!')


if __name__ == '__main__':
    print('=== Migração: Sync Produção ===')
    run_migration()
