#!/usr/bin/env python3
"""
Script de migração para mover desenhos técnicos locais para Replit Object Storage.

Este script:
1. Busca todas as especificações com desenhos técnicos
2. Faz upload dos desenhos locais para o Object Storage
3. Atualiza os caminhos no banco de dados
4. Mantém fallback para arquivos que já estão no Object Storage
"""

import os
import sys
try:
    from replit.object_storage import Client
except ImportError:
    Client = None
from app import app, db, Specification

def migrate_drawings():
    """Migra desenhos técnicos para Object Storage"""
    
    with app.app_context():
        # Buscar todas as especificações com desenhos técnicos
        specs_with_drawings = Specification.query.filter(
            Specification.technical_drawing_url.isnot(None),
            Specification.technical_drawing_url != ''
        ).all()
        
        print(f"📊 Encontradas {len(specs_with_drawings)} especificações com desenhos técnicos")
        
        if not specs_with_drawings:
            print("✅ Nenhuma migração necessária!")
            return
        
        storage_client = Client()
        migrated = 0
        skipped = 0
        errors = 0
        
        for spec in specs_with_drawings:
            drawing_url = spec.technical_drawing_url
            
            # Pular URLs externas (legacy)
            if drawing_url.startswith('http://') or drawing_url.startswith('https://'):
                print(f"⏭️  Spec #{spec.id}: URL externa, pulando")
                skipped += 1
                continue
            
            # Verificar se já está no Object Storage
            if drawing_url.startswith('technical-drawings/'):
                try:
                    if storage_client.exists(drawing_url):
                        print(f"✅ Spec #{spec.id}: Já está no Object Storage")
                        skipped += 1
                        continue
                except Exception as e:
                    print(f"⚠️  Spec #{spec.id}: Erro ao verificar Object Storage: {e}")
            
            # Caminho local
            local_path = os.path.join(app.config['UPLOAD_FOLDER'], drawing_url)
            
            if not os.path.exists(local_path):
                print(f"❌ Spec #{spec.id}: Arquivo local não encontrado: {drawing_url}")
                errors += 1
                continue
            
            try:
                # Ler arquivo local
                with open(local_path, 'rb') as f:
                    image_data = f.read()
                
                # Gerar novo caminho no Object Storage
                filename = os.path.basename(drawing_url)
                storage_path = f"technical-drawings/{filename}"
                
                # Fazer upload
                storage_client.upload_from_bytes(storage_path, image_data)
                print(f"📤 Spec #{spec.id}: Upload concluído - {storage_path}")
                
                # Atualizar banco de dados
                spec.technical_drawing_url = storage_path
                db.session.commit()
                
                migrated += 1
                print(f"✅ Spec #{spec.id}: Migrado com sucesso!")
                
            except Exception as e:
                print(f"❌ Spec #{spec.id}: Erro ao migrar: {e}")
                errors += 1
                db.session.rollback()
        
        # Resumo
        print("\n" + "="*50)
        print("📊 RESUMO DA MIGRAÇÃO")
        print("="*50)
        print(f"Total de especificações: {len(specs_with_drawings)}")
        print(f"✅ Migradas com sucesso: {migrated}")
        print(f"⏭️  Puladas (já migradas ou URLs externas): {skipped}")
        print(f"❌ Erros: {errors}")
        print("="*50)
        
        if migrated > 0:
            print("\n🎉 Migração concluída! Os desenhos agora estão no Object Storage.")
            print("💡 Os arquivos locais podem ser removidos manualmente se desejado.")
        else:
            print("\n✅ Nenhuma migração necessária.")

if __name__ == '__main__':
    print("🚀 Iniciando migração de desenhos técnicos para Object Storage...")
    print("="*50 + "\n")
    
    try:
        migrate_drawings()
    except KeyboardInterrupt:
        print("\n\n⚠️  Migração interrompida pelo usuário.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Erro fatal durante migração: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
