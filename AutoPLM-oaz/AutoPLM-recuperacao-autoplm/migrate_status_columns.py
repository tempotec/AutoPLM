#!/usr/bin/env python3
"""
Script de Migração: Adicionar colunas status_changed_at, status_completed_at, is_imported, import_category
Banco de dados: PostgreSQL (Neon)
Modelo: Specification

Este script adiciona as colunas necessárias à tabela 'specification'.
Se as colunas já existem, o script será ignorado com segurança.
"""

import os
import sys
from dotenv import load_dotenv
from app import create_app
from app.extensions import db

def migrate():
    """Executa a migração de forma segura"""
    
    # Carregar variáveis de ambiente
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(env_path)
    
    # Criar app e contexto
    app = create_app()
    
    with app.app_context():
        try:
            print("🔍 Iniciando migração das colunas de status...")
            print(f"📊 Banco de dados: PostgreSQL (Neon)")
            
            # Conectar ao banco
            connection = db.engine.raw_connection()
            cursor = connection.cursor()
            
            try:
                # Verificar se as colunas já existem
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'specification'
                    AND column_name IN ('status_changed_at', 'status_completed_at', 'is_imported', 'import_category')
                """)
                existing_columns = {row[0] for row in cursor.fetchall()}
                
                # Adicionar status_changed_at se não existir
                if 'status_changed_at' not in existing_columns:
                    print("➕ Adicionando coluna 'status_changed_at'...")
                    cursor.execute("""
                        ALTER TABLE specification 
                        ADD COLUMN status_changed_at TIMESTAMP
                    """)
                    print("✅ Coluna 'status_changed_at' adicionada com sucesso!")
                else:
                    print("⏭️  Coluna 'status_changed_at' já existe, ignorando...")
                
                # Adicionar status_completed_at se não existir
                if 'status_completed_at' not in existing_columns:
                    print("➕ Adicionando coluna 'status_completed_at'...")
                    cursor.execute("""
                        ALTER TABLE specification 
                        ADD COLUMN status_completed_at TIMESTAMP
                    """)
                    print("✅ Coluna 'status_completed_at' adicionada com sucesso!")
                else:
                    print("⏭️  Coluna 'status_completed_at' já existe, ignorando...")
                
                # Adicionar is_imported se n??o existir
                if 'is_imported' not in existing_columns:
                    print("?z\x07 Adicionando coluna 'is_imported'...")
                    cursor.execute("""
                        ALTER TABLE specification 
                        ADD COLUMN is_imported BOOLEAN DEFAULT FALSE
                    """)
                    print("?o. Coluna 'is_imported' adicionada com sucesso!")
                else:
                    print("??????  Coluna 'is_imported' j?? existe, ignorando...")

                # Adicionar import_category se n??o existir
                if 'import_category' not in existing_columns:
                    print("?z\x07 Adicionando coluna 'import_category'...")
                    cursor.execute("""
                        ALTER TABLE specification 
                        ADD COLUMN import_category VARCHAR(50)
                    """)
                    print("?o. Coluna 'import_category' adicionada com sucesso!")
                else:
                    print("??????  Coluna 'import_category' j?? existe, ignorando...")

                connection.commit()
                print("\n✨ Migração concluída com sucesso!")
                return True
                
            except Exception as e:
                connection.rollback()
                print(f"\n❌ Erro ao executar migração: {e}")
                return False
            finally:
                cursor.close()
                connection.close()
                
        except Exception as e:
            print(f"\n❌ Erro ao conectar ao banco de dados: {e}")
            print("💡 Verifique se DATABASE_URL está correto em .env")
            return False

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)