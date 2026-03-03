"""
Migração: Adicionar colunas do Fluxogama ao FichaTecnicaItem
============================================================
Adiciona: colecao, fluxogama_status, fluxogama_sent_at, fluxogama_response

Executar: python migrate_fluxogama.py
"""
import os
import sys

os.environ.setdefault('APP_ENV', 'development')

from app import create_app
from app.extensions import db

app = create_app()

COLUMNS_TO_ADD = [
    ("ficha_tecnica_item", "colecao", "VARCHAR(255)"),
    ("ficha_tecnica_item", "fluxogama_status", "VARCHAR(50)"),
    ("ficha_tecnica_item", "fluxogama_sent_at", "TIMESTAMP"),
    ("ficha_tecnica_item", "fluxogama_response", "TEXT"),
]


def column_exists(conn, table, column):
    """Check if column exists in table (works for PostgreSQL and SQLite)."""
    dialect = db.engine.dialect.name
    if dialect == 'postgresql':
        result = conn.execute(db.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :table AND column_name = :column"
        ), {"table": table, "column": column})
        return result.fetchone() is not None
    else:  # SQLite
        result = conn.execute(db.text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result.fetchall())


def run_migration():
    with app.app_context():
        conn = db.engine.connect()
        added = []
        skipped = []

        for table, column, col_type in COLUMNS_TO_ADD:
            if column_exists(conn, table, column):
                skipped.append(f"  [SKIP] {table}.{column} (já existe)")
            else:
                conn.execute(db.text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                ))
                conn.commit()
                added.append(f"  [ADD]  {table}.{column} ({col_type})")

        if added:
            print("Colunas adicionadas:")
            for msg in added:
                print(msg)
        if skipped:
            print("Colunas já existentes (ignoradas):")
            for msg in skipped:
                print(msg)
        if not added and not skipped:
            print("Nenhuma coluna para processar.")

        conn.close()
        print("\nMigração concluída com sucesso!")


if __name__ == '__main__':
    run_migration()
