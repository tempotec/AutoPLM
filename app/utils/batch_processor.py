"""
Processamento em lote com checkpoint por etapas.

Etapas de processamento:
0 = pending (aguardando)
1 = thumbnail (gerar thumbnail)
2 = extract_image (extrair imagem do produto)
3 = extract_text (extrair texto do PDF)
4 = openai_parse (processar com OpenAI)
5 = supplier_link (vincular fornecedor)
6 = completed (finalizado)
"""

import os
import re
import json
import threading
import time
from datetime import datetime

STAGE_PENDING = 0
STAGE_THUMBNAIL = 1
STAGE_EXTRACT_IMAGE = 2
STAGE_EXTRACT_TEXT = 3
STAGE_OPENAI_PARSE = 4
STAGE_SUPPLIER_LINK = 5
STAGE_COMPLETED = 6

STAGE_NAMES = {
    0: 'pending',
    1: 'thumbnail',
    2: 'extract_image',
    3: 'extract_text',
    4: 'openai_parse',
    5: 'supplier_link',
    6: 'completed'
}


def get_file_path_for_spec(spec, upload_folder):
    return os.path.join(upload_folder, spec.pdf_filename)


def process_stage_thumbnail(spec, file_path, thread_session):
    from app.utils.files import is_image_file, is_pdf_file
    from app.utils.pdf import generate_pdf_thumbnail, generate_image_thumbnail
    
    filename = spec.pdf_filename
    
    if is_image_file(filename):
        print(f"[ETAPA 1] Gerando thumbnail da imagem: {filename}")
        thumbnail_url = generate_image_thumbnail(file_path, spec.id)
        if thumbnail_url:
            spec.pdf_thumbnail = thumbnail_url
            print(f"  ✓ Thumbnail gerado: {thumbnail_url}")
    elif is_pdf_file(filename):
        print(f"[ETAPA 1] Gerando thumbnail do PDF: {filename}")
        thumbnail_url = generate_pdf_thumbnail(file_path, spec.id)
        if thumbnail_url:
            spec.pdf_thumbnail = thumbnail_url
            print(f"  ✓ Thumbnail gerado: {thumbnail_url}")
    
    spec.processing_stage = STAGE_THUMBNAIL
    thread_session.commit()
    return True


def process_stage_extract_image(spec, file_path, thread_session):
    filename = spec.pdf_filename
    if filename:
        print(f"[ETAPA 2] Pulando extracao de imagem para processamento: {filename}")
        print("  Desenho tecnico e gerado separadamente.")

    spec.processing_stage = STAGE_EXTRACT_IMAGE
    thread_session.commit()
    return True


def process_stage_extract_text(spec, file_path, thread_session):
    from app.utils.files import is_image_file, is_pdf_file
    from app.utils.pdf import extract_text_from_pdf, extract_text_from_image

    filename = spec.pdf_filename

    if is_image_file(filename):
        print(f"[ETAPA 3] Extraindo texto via OCR da imagem: {filename}")
        text_content = extract_text_from_image(file_path)
        if text_content and len(text_content.strip()) >= 50:
            spec.raw_extracted_text = text_content
            print(f"  Texto OCR extraido: {len(text_content)} caracteres")
        else:
            spec.raw_extracted_text = ""
            print("  OCR insuficiente; usando fallback visual.")

    elif is_pdf_file(filename):
        print(f"[ETAPA 3] Extraindo texto do PDF: {filename}")
        text_content = extract_text_from_pdf(file_path)

        if not text_content or len(text_content.strip()) < 50:
            raise Exception(f"Texto insuficiente extraido do PDF ({len(text_content) if text_content else 0} chars)")

        spec.raw_extracted_text = text_content
        print(f"  Texto extraido: {len(text_content)} caracteres")

    spec.processing_stage = STAGE_EXTRACT_TEXT
    thread_session.commit()
    return True


def process_stage_openai_parse(spec, file_path, thread_session):
    from app.utils.files import is_image_file, is_pdf_file, convert_image_to_base64
    from app.utils.ai import analyze_images_with_gpt4_vision, process_specification_with_openai

    filename = spec.pdf_filename

    if is_image_file(filename):
        text_content = spec.raw_extracted_text
        extracted_data = None
        if text_content and len(text_content.strip()) >= 50:
            print(f"[ETAPA 4] Processando OCR com OpenAI: {filename}")
            extracted_data = process_specification_with_openai(text_content)

        if extracted_data:
            _apply_extracted_data_to_spec(spec, extracted_data)
        else:
            print(f"[ETAPA 4] Analisando imagem com GPT-4o Vision: {filename}")
            image_b64 = convert_image_to_base64(file_path)
            if not image_b64:
                raise Exception("Erro ao converter imagem para base64")

            visual_analysis = analyze_images_with_gpt4_vision([image_b64])

            if not visual_analysis:
                raise Exception("Erro na analise visual da imagem")

            if isinstance(visual_analysis, dict):
                _apply_visual_analysis_to_spec(spec, visual_analysis)
            else:
                extracted_data = process_specification_with_openai(str(visual_analysis))
                if extracted_data:
                    _apply_extracted_data_to_spec(spec, extracted_data)
                else:
                    spec.description = "Peca de Vestuario (Imagem)"

    elif is_pdf_file(filename):
        print(f"[ETAPA 4] Processando texto com OpenAI: {filename}")
        text_content = spec.raw_extracted_text

        if not text_content:
            raise Exception("Texto nao encontrado - etapa 3 nao foi concluida")

        extracted_data = process_specification_with_openai(text_content)

        if not extracted_data:
            raise Exception("OpenAI nao retornou dados extraidos")

        _apply_extracted_data_to_spec(spec, extracted_data)

    spec.processing_stage = STAGE_OPENAI_PARSE
    thread_session.commit()
    return True


def process_stage_supplier_link(spec, file_path, thread_session):
    from app.utils.helpers import get_or_create_supplier
    
    print(f"[ETAPA 5] Vinculando fornecedor: {spec.pdf_filename}")
    
    if spec.supplier and not spec.supplier_id:
        supplier = get_or_create_supplier(spec.supplier, spec.user_id, thread_session)
        if supplier:
            spec.supplier_id = supplier.id
            print(f"  ✓ Fornecedor vinculado: {supplier.name} (ID: {supplier.id})")
    else:
        print(f"  ✓ Fornecedor já vinculado ou não detectado")
    
    spec.processing_stage = STAGE_SUPPLIER_LINK
    thread_session.commit()
    return True


def process_stage_complete(spec, thread_session):
    print(f"[ETAPA 6] Finalizando processamento: {spec.pdf_filename}")
    spec.processing_stage = STAGE_COMPLETED
    spec.processing_status = 'completed'
    spec.last_error = None
    spec.error_stage = None
    thread_session.commit()
    print(f"  ✓ Processamento concluído com sucesso!")
    return True


def _apply_visual_analysis_to_spec(spec, visual_analysis):
    ident = visual_analysis.get('identificacao', {})
    gola = visual_analysis.get('gola_decote', {})
    mangas = visual_analysis.get('mangas', {})
    corpo = visual_analysis.get('corpo', {})
    textura = visual_analysis.get('textura_padronagem', {})
    
    tipo_peca = ident.get('tipo_peca', '')
    categoria = ident.get('categoria', '')
    grupo = ident.get('grupo', '')
    subgrupo = ident.get('subgrupo', '')
    
    spec.description = f"{tipo_peca}" if tipo_peca else "Peça de Vestuário (Imagem)"
    spec.composition = categoria if categoria else None
    
    if textura.get('tipo_trico_malha') and textura['tipo_trico_malha'] != 'nao_visivel':
        pattern_parts = [textura['tipo_trico_malha']]
        if textura.get('direcao') and textura['direcao'] != 'nao_visivel':
            pattern_parts.append(textura['direcao'])
        if textura.get('rapport_ou_repeticao'):
            pattern_parts.append(textura['rapport_ou_repeticao'])
        spec.pattern = ' - '.join(pattern_parts)
    else:
        spec.pattern = None
    
    spec.main_group = grupo if grupo else None
    spec.sub_group = subgrupo if subgrupo else None
    
    detalhes = []
    if gola.get('tipo') and gola['tipo'] != 'nao_visivel':
        detalhes.append(f"Gola: {gola['tipo']}")
    if mangas.get('comprimento') and mangas['comprimento'] != 'nao_visivel':
        detalhes.append(f"Mangas: {mangas['comprimento']}")
    if corpo.get('comprimento_visual'):
        detalhes.append(f"Comprimento: {corpo['comprimento_visual']}")
    
    if detalhes:
        spec.finishes = ' | '.join(detalhes)
    
    print(f"  ✓ Dados extraídos: {spec.description}, Grupo: {spec.main_group}")


def _apply_extracted_data_to_spec(spec, extracted_data):
    from app.utils.helpers import convert_value_to_string
    
    for key, value in extracted_data.items():
        if hasattr(spec, key) and value is not None:
            if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                if isinstance(value, str):
                    if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                        continue
            setattr(spec, key, convert_value_to_string(value))
    
    print(f"  ✓ Dados extraídos: {spec.description}, Fornecedor: {spec.supplier}")


def advance_spec_processing(spec_id, upload_folder, app):
    from sqlalchemy.orm import sessionmaker
    from app.extensions import db
    from app.models import Specification
    
    Session = sessionmaker(bind=db.engine)
    thread_session = Session()
    spec = None
    
    try:
        spec = thread_session.query(Specification).get(spec_id)
        if not spec:
            print(f"Specification {spec_id} not found")
            thread_session.close()
            return False
        
        file_path = get_file_path_for_spec(spec, upload_folder)
        current_stage = spec.processing_stage or 0
        
        print(f"\n{'='*60}")
        print(f"PROCESSANDO: {spec.pdf_filename} (ID: {spec_id})")
        print(f"Etapa atual: {current_stage} ({STAGE_NAMES.get(current_stage, 'unknown')})")
        print(f"{'='*60}")
        
        stages = [
            (STAGE_PENDING, STAGE_THUMBNAIL, process_stage_thumbnail),
            (STAGE_THUMBNAIL, STAGE_EXTRACT_IMAGE, process_stage_extract_image),
            (STAGE_EXTRACT_IMAGE, STAGE_EXTRACT_TEXT, process_stage_extract_text),
            (STAGE_EXTRACT_TEXT, STAGE_OPENAI_PARSE, process_stage_openai_parse),
            (STAGE_OPENAI_PARSE, STAGE_SUPPLIER_LINK, process_stage_supplier_link),
            (STAGE_SUPPLIER_LINK, STAGE_COMPLETED, lambda s, f, t: process_stage_complete(s, t)),
        ]
        
        for from_stage, to_stage, stage_func in stages:
            if current_stage <= from_stage:
                try:
                    spec.processing_status = 'processing'
                    thread_session.commit()
                    
                    stage_func(spec, file_path, thread_session)
                    current_stage = spec.processing_stage
                    
                except Exception as stage_error:
                    print(f"  ❌ Erro na etapa {to_stage}: {stage_error}")
                    spec.last_error = str(stage_error)
                    spec.error_stage = to_stage
                    spec.retry_count = (spec.retry_count or 0) + 1
                    spec.processing_status = 'error'
                    thread_session.commit()
                    thread_session.close()
                    return False
        
        thread_session.close()
        return True
        
    except Exception as e:
        print(f"Erro geral no processamento: {e}")
        import traceback
        traceback.print_exc()
        
        try:
            if spec is not None:
                spec.processing_status = 'error'
                spec.last_error = str(e)
                thread_session.commit()
        except:
            pass
        finally:
            thread_session.close()
        
        return False


def process_batch_queue(batch_id, upload_folder, app, batch_size=5):
    from sqlalchemy.orm import sessionmaker
    from app.extensions import db
    from app.models import Specification
    
    print(f"\n{'='*80}")
    print(f"INICIANDO PROCESSAMENTO EM LOTE: {batch_id}")
    print(f"Tamanho do bloco: {batch_size}")
    print(f"{'='*80}\n")
    
    with app.app_context():
        Session = sessionmaker(bind=db.engine)
        
        while True:
            session = Session()
            
            pending_specs = session.query(Specification).filter(
                Specification.batch_id == batch_id,
                Specification.processing_status.in_(['pending', 'processing', 'error']),
                Specification.processing_stage < STAGE_COMPLETED
            ).order_by(Specification.id).limit(batch_size).all()
            
            if not pending_specs:
                print(f"\n✓ Lote {batch_id} concluído - nenhum arquivo pendente")
                session.close()
                break
            
            spec_ids = [s.id for s in pending_specs]
            session.close()
            
            print(f"\nProcessando bloco de {len(spec_ids)} arquivos: {spec_ids}")
            
            for spec_id in spec_ids:
                try:
                    success = advance_spec_processing(spec_id, upload_folder, app)
                    if success:
                        print(f"  ✓ Spec {spec_id} processado com sucesso")
                    else:
                        print(f"  ⚠️ Spec {spec_id} falhou - continuando com próximo")
                except Exception as e:
                    print(f"  ❌ Erro ao processar spec {spec_id}: {e}")
            
            time.sleep(0.5)
    
    print(f"\n{'='*80}")
    print(f"LOTE {batch_id} FINALIZADO")
    print(f"{'='*80}\n")


def start_batch_processing(batch_id, upload_folder, app, batch_size=5):
    thread = threading.Thread(
        target=process_batch_queue,
        args=(batch_id, upload_folder, app, batch_size),
        daemon=True
    )
    thread.start()
    return thread
