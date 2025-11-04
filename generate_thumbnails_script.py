#!/usr/bin/env python3
"""Script to generate thumbnails for all PDFs without them"""
import os
import sys

# Ensure pymupdf is available
try:
    import pymupdf as fitz
except ImportError:
    print("Error: PyMuPDF não está instalado. Por favor instale com: pip install pymupdf")
    sys.exit(1)

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Specification, generate_pdf_thumbnail

def generate_all_thumbnails():
    """Generate thumbnails for all PDFs that don't have them yet"""
    with app.app_context():
        try:
            # Find all specifications with PDFs but no thumbnails
            specs = Specification.query.filter(
                Specification.pdf_filename.like('%.pdf'),
                Specification.pdf_thumbnail.is_(None)
            ).all()
            
            if not specs:
                print('✓ Todos os PDFs já têm thumbnails!')
                return
            
            print(f"Encontrados {len(specs)} PDFs sem thumbnail")
            print("="*80)
            
            processed = 0
            errors = 0
            
            for spec in specs:
                try:
                    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], spec.pdf_filename)
                    
                    if not os.path.exists(pdf_path):
                        print(f"✗ PDF não encontrado: {pdf_path}")
                        errors += 1
                        continue
                    
                    print(f"Processando spec #{spec.id}: {spec.pdf_filename}")
                    thumbnail_url = generate_pdf_thumbnail(pdf_path, spec.id)
                    
                    if thumbnail_url:
                        spec.pdf_thumbnail = thumbnail_url
                        db.session.commit()
                        processed += 1
                        print(f"  ✓ Thumbnail gerado: {thumbnail_url}\n")
                    else:
                        errors += 1
                        print(f"  ✗ Erro ao gerar thumbnail\n")
                        
                except Exception as e:
                    errors += 1
                    print(f"  ✗ Erro: {e}\n")
                    continue
            
            print("="*80)
            print(f"RESULTADO: {processed} thumbnails gerados com sucesso!")
            if errors > 0:
                print(f"           {errors} erros encontrados")
                
        except Exception as e:
            print(f'Erro ao gerar thumbnails: {str(e)}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    generate_all_thumbnails()
