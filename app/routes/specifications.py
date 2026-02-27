import os
import threading
import re
import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from app.extensions import db, get_openai_client
from app.models import User, Specification, Collection, Supplier
from app.forms import UploadPDFForm, SpecificationForm
from app.utils.auth import login_required
from app.utils.files import is_image_file, is_pdf_file, convert_image_to_data_url
from app.utils.pdf import extract_text_from_pdf, extract_text_from_image, generate_pdf_thumbnail, generate_image_thumbnail
from app.utils.ai import analyze_images_with_gpt4_vision, process_specification_with_openai
from app.utils.helpers import convert_value_to_string, get_or_create_supplier
from app.utils.logging import log_activity, rpa_info, rpa_error

specifications_bp = Blueprint('specifications', __name__)


def save_product_image(spec_id, image_b64_or_path, is_b64=True):
    try:
        import uuid
        import base64
        product_image_filename = f"product_{spec_id}_{uuid.uuid4().hex[:8]}.png"
        product_images_dir = os.path.join(current_app.static_folder, 'product_images')
        os.makedirs(product_images_dir, exist_ok=True)
        product_image_path = os.path.join(product_images_dir, product_image_filename)

        if is_b64:
            image_data = base64.b64decode(
                image_b64_or_path.split(',')[1] if ',' in image_b64_or_path else image_b64_or_path)
            with open(product_image_path, 'wb') as f:
                f.write(image_data)
        else:
            import shutil
            shutil.copy(image_b64_or_path, product_image_path)

        return f"/static/product_images/{product_image_filename}"
    except Exception as e:
        print(f"Error saving product image: {e}")
        return None


def process_pdf_specification(spec_id, file_path, app):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db.engine)
    thread_session = Session()

    try:
        spec = thread_session.query(Specification).get(spec_id)
        if not spec:
            print(f"Specification {spec_id} not found")
            thread_session.close()
            return

        filename = spec.pdf_filename

        if is_image_file(filename):
            print(f"\n{'='*80}")
            print(f"PROCESSAMENTO DE IMAGEM DETECTADO: {filename}")
            print(f"{'='*80}\n")

            thumbnail_url = generate_image_thumbnail(file_path, spec_id)
            if thumbnail_url:
                spec.pdf_thumbnail = thumbnail_url
                print(f"✓ Thumbnail da imagem gerado: {thumbnail_url}")

            print("Arquivo de imagem detectado: iniciando OCR e/ou analise visual.")

            ocr_text = extract_text_from_image(file_path)
            extracted_data = None
            if ocr_text and len(ocr_text.strip()) >= 50:
                extracted_data = process_specification_with_openai(ocr_text)

            if extracted_data:
                for key, value in extracted_data.items():
                    if hasattr(spec, key) and value is not None:
                        if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                            if isinstance(value, str):
                                if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                                    print(f"  ⚠️ Ignorando data invalida para {key}: {value}")
                                    continue
                        setattr(spec, key, convert_value_to_string(value))

                supplier_name = extracted_data.get('supplier')
                if supplier_name and isinstance(supplier_name, str) and supplier_name.strip():
                    print(f"\nFornecedor detectado no OCR: {supplier_name}")
                    supplier = get_or_create_supplier(supplier_name, spec.user_id, thread_session)
                    if supplier:
                        spec.supplier_id = supplier.id
                        spec.supplier = supplier.name
            else:
                image_data_url = convert_image_to_data_url(file_path)
                if not image_data_url:
                    print("Erro ao converter imagem para base64")
                    spec.processing_status = 'error'
                    thread_session.commit()
                    thread_session.close()
                    return

                visual_analysis = analyze_images_with_gpt4_vision([image_data_url])

                if not visual_analysis:
                    print("Erro na analise visual da imagem")
                    spec.processing_status = 'error'
                    thread_session.commit()
                    thread_session.close()
                    return

                if isinstance(visual_analysis, dict):
                    ident = visual_analysis.get('identificacao', {})
                    gola = visual_analysis.get('gola_decote', {})
                    mangas = visual_analysis.get('mangas', {})
                    corpo = visual_analysis.get('corpo', {})
                    textura = visual_analysis.get('textura_padronagem', {})

                    tipo_peca = ident.get('tipo_peca', '')
                    categoria = ident.get('categoria', '')
                    grupo = ident.get('grupo', '')
                    subgrupo = ident.get('subgrupo', '')

                    spec.description = f"{tipo_peca}" if tipo_peca else "Peca de Vestuario (Imagem)"
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

                    print("Dados extraidos da analise visual (JSON estruturado):")
                    print(f"  - Descricao: {spec.description}")
                    print(f"  - Categoria: {spec.composition}")
                    print(f"  - Grupo: {spec.main_group}")
                    print(f"  - Subgrupo: {spec.sub_group}")
                else:
                    print("Analise visual retornou texto (fallback de JSON)")
                    visual_text = str(visual_analysis)
                    extracted_data = process_specification_with_openai(visual_text)

                    if extracted_data:
                        for key, value in extracted_data.items():
                            if hasattr(spec, key) and value is not None:
                                if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                                    if isinstance(value, str):
                                        if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                                            print(f"  ⚠️ Ignorando data invalida para {key}: {value}")
                                            continue
                                setattr(spec, key, convert_value_to_string(value))

                        supplier_name = extracted_data.get('supplier')
                        if supplier_name and isinstance(supplier_name, str) and supplier_name.strip():
                            print(f"\nFornecedor detectado na analise: {supplier_name}")
                            supplier = get_or_create_supplier(supplier_name, spec.user_id, thread_session)
                            if supplier:
                                spec.supplier_id = supplier.id
                                spec.supplier = supplier.name
                    else:
                        spec.description = "Peca de Vestuario (Imagem)"

            spec.processing_status = 'completed'
            thread_session.commit()
            thread_session.close()
            print("Imagem processada com sucesso!")
            return

        elif is_pdf_file(filename):
            print(f"\n{'='*80}")
            print(f"PROCESSAMENTO DE PDF DETECTADO: {filename}")
            print(f"{'='*80}\n")

            thumbnail_url = generate_pdf_thumbnail(file_path, spec_id)
            if thumbnail_url:
                spec.pdf_thumbnail = thumbnail_url
                print(f"✓ Thumbnail do PDF gerado: {thumbnail_url}")

            text_content = extract_text_from_pdf(file_path)

            if not text_content or len(text_content.strip()) < 50:
                print(f"Insufficient text extracted from PDF for spec {spec_id}")
                spec.processing_status = 'error'
                thread_session.commit()
                thread_session.close()
                return

            extracted_data = process_specification_with_openai(text_content)

            if not extracted_data:
                print(f"No data extracted from OpenAI for spec {spec_id}")
                spec.processing_status = 'error'
                thread_session.commit()
                thread_session.close()
                return

            for key, value in extracted_data.items():
                if hasattr(spec, key) and value is not None:
                    if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                        if isinstance(value, str):
                            if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                                print(f"  ⚠️ Ignorando data inválida para {key}: {value} (esperado YYYY-MM-DD)")
                                continue
                    setattr(spec, key, convert_value_to_string(value))

            supplier_name = extracted_data.get('supplier')
            if supplier_name and isinstance(supplier_name, str) and supplier_name.strip():
                print(f"\n{'='*80}")
                print(f"AUTO-CADASTRO DE FORNECEDOR")
                print(f"{'='*80}")
                print(f"📦 Fornecedor detectado no PDF: {supplier_name}")

                supplier = get_or_create_supplier(supplier_name, spec.user_id, thread_session)
                if supplier:
                    spec.supplier_id = supplier.id
                    spec.supplier = supplier.name
                    print(f"✓ Ficha técnica vinculada ao fornecedor ID {supplier.id}")
                else:
                    print(f"⚠️ Não foi possível cadastrar o fornecedor")
                print(f"{'='*80}\n")

            spec.processing_status = 'completed'
            thread_session.commit()
            thread_session.close()
            print(f"Successfully processed PDF specification {spec_id}")
        else:
            print(f"⚠️ Formato de arquivo não reconhecido: {filename}")
            spec.processing_status = 'error'
            thread_session.commit()
            thread_session.close()

    except Exception as e:
        print(f"Error processing specification {spec_id}: {e}")
        import traceback
        traceback.print_exc()

        try:
            if spec:
                spec.processing_status = 'error'
                thread_session.commit()
        except Exception as update_error:
            print(f"Error updating specification status: {update_error}")
        finally:
            thread_session.close()


@specifications_bp.route('/upload_pdf', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadPDFForm()

    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    if user.is_admin:
        user_collections = Collection.query.order_by(Collection.name).all()
        user_suppliers = Supplier.query.order_by(Supplier.name).all()
    else:
        user_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()
        user_suppliers = Supplier.query.filter_by(user_id=user.id).order_by(Supplier.name).all()

    form.collection_id.choices = [(0, '-- Sem coleção --')] + [(c.id, c.name) for c in user_collections]


    form.supplier_id.choices = [(0, '-- Sem fornecedor --')] + [(s.id, s.name) for s in user_suppliers]

    from app.models.fluxogama_subetapa import FluxogamaSubetapa
    from app.utils.helpers import normalize_wsid
    subetapas = FluxogamaSubetapa.query.filter_by(ativo=True, colecao_wsid=None).order_by(FluxogamaSubetapa.nome).all()

    if request.method == 'GET':
        form.stylist.data = user.username

    if request.method == 'POST':
        try:
            files = request.files.getlist('pdf_file')
            
            if not files or len(files) == 0 or (len(files) == 1 and files[0].filename == ''):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado'})
                flash('Por favor, selecione um arquivo.')
                return render_template('upload_pdf.html', form=form, current_user=user)
            
            if len(files) == 1:
                file = files[0]
                filename = secure_filename(file.filename)
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                spec = Specification()
                spec.user_id = session['user_id']
                spec.pdf_filename = filename
                spec.collection_id = form.collection_id.data if form.collection_id.data and form.collection_id.data != 0 else None

                if form.supplier_id.data and form.supplier_id.data != 0:
                    spec.supplier_id = form.supplier_id.data
                    selected_supplier = Supplier.query.get(form.supplier_id.data)
                    spec.supplier = selected_supplier.name if selected_supplier else None
                else:
                    spec.supplier_id = None
                    spec.supplier = None

                spec.stylists = form.stylist.data or user.username
                spec.price_range = form.price_range.data if form.price_range.data else None
                spec.fluxogama_subetapa = normalize_wsid(request.form.get('fluxogama_subetapa', ''))
                spec.is_imported = bool(form.is_imported.data)
                spec.import_category = form.import_category.data if spec.is_imported else None
                spec.processing_status = 'processing'
                spec.created_at = datetime.now()
                spec.set_status('in_development')

                db.session.add(spec)
                db.session.commit()

                spec_id = spec.id
                
                log_activity('UPLOAD_FILE', 'specification', spec_id, 
                            target_name=spec.description or filename,
                            metadata={'filename': filename, 'collection_id': spec.collection_id, 'supplier_id': spec.supplier_id})
                rpa_info(f"UPLOAD: Arquivo '{filename}' enviado pelo usuário '{user.username}'")

                app = current_app._get_current_object()

                def process_in_background():
                    with app.app_context():
                        try:
                            rpa_info(f"PROCESSAMENTO: Iniciando processamento do arquivo '{filename}' (ID: {spec_id})")
                            process_pdf_specification(spec_id, file_path, app)
                            rpa_info(f"PROCESSAMENTO: Arquivo '{filename}' (ID: {spec_id}) processado com sucesso")
                        except Exception as e:
                            print(f"❌ Error in background processing thread: {e}")
                            import traceback
                            traceback.print_exc()
                            rpa_error(f"PROCESSAMENTO_ERRO: Falha ao processar '{filename}' (ID: {spec_id})", exc=e, regiao="processamento")
                            try:
                                error_spec = Specification.query.get(spec_id)
                                if error_spec:
                                    error_spec.processing_status = 'error'
                                    db.session.commit()
                            except:
                                pass

                thread = threading.Thread(target=process_in_background)
                thread.daemon = True
                thread.start()

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': 'Arquivo enviado! Processamento iniciado em segundo plano.',
                        'spec_id': spec_id,
                        'filename': filename
                    })

                flash('Arquivo enviado! Processamento iniciado em segundo plano.')
                return redirect(url_for('dashboard.index'))
            
            else:
                import uuid
                from app.utils.batch_processor import start_batch_processing
                
                batch_id = str(uuid.uuid4())[:8]
                collection_id = form.collection_id.data if form.collection_id.data and form.collection_id.data != 0 else None
                supplier_id = form.supplier_id.data if form.supplier_id.data and form.supplier_id.data != 0 else None
                stylist = form.stylist.data or user.username
                price_range = form.price_range.data if form.price_range.data else None
                
                supplier_name = None
                if supplier_id:
                    selected_supplier = Supplier.query.get(supplier_id)
                    supplier_name = selected_supplier.name if selected_supplier else None
                
                spec_ids = []
                for file in files:
                    if file.filename:
                        filename = secure_filename(file.filename)
                        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                        file.save(file_path)
                        
                        spec = Specification()
                        spec.user_id = session['user_id']
                        spec.pdf_filename = filename
                        spec.collection_id = collection_id
                        spec.supplier_id = supplier_id
                        spec.supplier = supplier_name
                        spec.stylists = stylist
                        spec.price_range = price_range
                        spec.fluxogama_subetapa = normalize_wsid(request.form.get('fluxogama_subetapa', ''))
                        spec.is_imported = bool(form.is_imported.data)
                        spec.import_category = form.import_category.data if spec.is_imported else None
                        spec.processing_status = 'pending'
                        spec.processing_stage = 0
                        spec.batch_id = batch_id
                        spec.created_at = datetime.now()
                        spec.set_status('in_development')
                        
                        db.session.add(spec)
                        db.session.flush()
                        spec_ids.append(spec.id)
                
                db.session.commit()
                
                log_activity('BATCH_UPLOAD', 'specification', None,
                            target_name=f'Lote {batch_id}',
                            metadata={'batch_id': batch_id, 'file_count': len(spec_ids), 'collection_id': collection_id})
                rpa_info(f"BATCH_UPLOAD: {len(spec_ids)} arquivos enviados pelo usuário '{user.username}' (lote {batch_id})")
                
                app = current_app._get_current_object()
                start_batch_processing(batch_id, current_app.config['UPLOAD_FOLDER'], app)
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    specs_created = Specification.query.filter(Specification.id.in_(spec_ids)).all()
                    specs_data = []
                    for idx, sid in enumerate(spec_ids):
                        spec_obj = next((s for s in specs_created if s.id == sid), None)
                        specs_data.append({
                            'id': sid,
                            'index': idx,
                            'filename': spec_obj.pdf_filename if spec_obj else '',
                            'status': 'pending'
                        })
                    return jsonify({
                        'success': True,
                        'message': f'{len(spec_ids)} arquivos enviados! Processamento iniciado.',
                        'batch_id': batch_id,
                        'count': len(spec_ids),
                        'specs': specs_data
                    })
                
                flash(f'{len(spec_ids)} arquivos enviados! Processamento iniciado em segundo plano.')
                return redirect(url_for('dashboard.index'))

        except Exception as e:
            db.session.rollback()
            print(f"Error in upload_pdf: {e}")
            import traceback
            traceback.print_exc()
            rpa_error(f"UPLOAD_ERRO: Erro ao fazer upload do arquivo", exc=e, regiao="upload")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': str(e)})
            flash('Erro ao processar o arquivo. Por favor, tente novamente.')
            return render_template('upload_pdf.html', form=form, current_user=user, subetapas=subetapas)

    return render_template('upload_pdf.html', form=form, current_user=user, subetapas=subetapas)


@specifications_bp.route('/specification/<int:id>')
@login_required
def view(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    log_activity('VIEW_SPECIFICATION', 'specification', spec.id, 
                target_name=spec.description or spec.ref_souq)
    rpa_info(f"VIEW_SPEC: Visualização da especificação ID {spec.id}")
    extra_fields = {}
    if spec.extra_fields:
        try:
            extra_fields = json.loads(spec.extra_fields)
        except (TypeError, ValueError):
            extra_fields = {}
    if not isinstance(extra_fields, dict):
        extra_fields = {}

    return render_template('view_specification.html', specification=spec, extra_fields=extra_fields)


@specifications_bp.route('/specification/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    form = SpecificationForm(obj=spec)

    if user.is_admin:
        user_collections = Collection.query.order_by(Collection.name).all()
    else:
        user_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()

    form.collection_id.choices = [(0, '-- Sem coleção --')] + [(c.id, c.name) for c in user_collections]
    if request.method == 'GET':
        form.status.data = spec.status

    if form.validate_on_submit():
        collection_id = form.collection_id.data if form.collection_id.data and form.collection_id.data != 0 else None
        form.populate_obj(spec)
        spec.collection_id = collection_id
        if form.status.data:
            spec.set_status(form.status.data)
        try:
            db.session.commit()
            log_activity('EDIT_SPECIFICATION', 'specification', spec.id,
                        target_name=spec.description or spec.ref_souq)
            rpa_info(f"EDIT_SPEC: Especificação ID {spec.id} atualizada")
            flash('Especificação atualizada com sucesso!')
            return redirect(url_for('specifications.view', id=spec.id))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar especificação.')

    
    elif request.method == 'POST' and form.errors:
        flash(f"Erro de validacao: {form.errors}")
    extra_fields = {}
    if spec.extra_fields:
        try:
            extra_fields = json.loads(spec.extra_fields)
        except (TypeError, ValueError):
            extra_fields = {}
    if not isinstance(extra_fields, dict):
        extra_fields = {}

    return render_template('edit_specification.html', form=form, specification=spec, extra_fields=extra_fields)


@specifications_bp.route('/specification/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    try:
        spec = Specification.query.get_or_404(id)
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('Sessão inválida. Por favor, faça login novamente.')
            return redirect(url_for('auth.login'))

        if not user.is_admin and spec.user_id != user.id:
            flash('Acesso negado.')
            return redirect(url_for('dashboard.index'))

        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        spec_name = spec.description or spec.ref_souq
        db.session.delete(spec)
        db.session.commit()
        log_activity('DELETE_SPECIFICATION', 'specification', id, target_name=spec_name)
        rpa_info(f"DELETE_SPEC: Especificação '{spec_name}' (ID: {id}) excluída")
        flash('Especificação excluída com sucesso!')
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Erro ao excluir especificação {id}: {e}")
        traceback.print_exc()
        rpa_error(f"DELETE_SPEC_ERRO: Erro ao excluir especificação ID {id}", exc=e, regiao="delete_spec")
        flash('Erro ao excluir especificação. Tente novamente.')

    return redirect(url_for('dashboard.index'))


@specifications_bp.route('/download_pdf/<int:id>')
@login_required
def download_pdf(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename)
        if os.path.exists(file_path):
            log_activity('DOWNLOAD_FILE', 'specification', spec.id, target_name=spec.pdf_filename)
            rpa_info(f"DOWNLOAD_FILE: Arquivo '{spec.pdf_filename}' baixado (ID: {spec.id})")
            return send_file(file_path, as_attachment=True, download_name=spec.pdf_filename)
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('specifications.view', id=id))
    except Exception as e:
        flash('Erro ao baixar o arquivo PDF.')
        return redirect(url_for('specifications.view', id=id))


@specifications_bp.route('/view_pdf/<int:id>')
@login_required
def view_pdf(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('SessWARNo invWARNlida. Por favor, faWARNa login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    try:
        file_path = os.path.abspath(os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename))
        if os.path.exists(file_path):
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=False,
                download_name=spec.pdf_filename,
            )
        print(f"View PDF not found: {file_path}")
        return 'Arquivo PDF nao encontrado.', 404
    except Exception as e:
        print(f"View PDF error: {e}")
        return 'Erro ao visualizar o arquivo PDF.', 500


@specifications_bp.route('/view_image/<int:id>')
@login_required
def view_image(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('SessWARNo invWARNlida. Por favor, faWARNa login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    try:
        file_path = os.path.abspath(os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename))
        if os.path.exists(file_path):
            ext = spec.pdf_filename.lower().split('.')[-1]
            mimetype_map = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png'
            }
            mimetype = mimetype_map.get(ext, 'image/jpeg')
            return send_file(
                file_path,
                mimetype=mimetype,
                as_attachment=False,
                download_name=spec.pdf_filename,
            )
        print(f"View image not found: {file_path}")
        return 'Arquivo de imagem nao encontrado.', 404
    except Exception as e:
        print(f"View image error: {e}")
        return 'Erro ao visualizar o arquivo de imagem.', 500


@specifications_bp.route('/upload_batch', methods=['GET', 'POST'])
@login_required
def upload_batch():
    from app.forms import BatchUploadForm
    from app.utils.batch_processor import start_batch_processing
    import uuid
    
    form = BatchUploadForm()
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))
    
    if user.is_admin:
        user_collections = Collection.query.order_by(Collection.name).all()
        user_suppliers = Supplier.query.order_by(Supplier.name).all()
    else:
        user_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()
        user_suppliers = Supplier.query.filter_by(user_id=user.id).order_by(Supplier.name).all()
    
    form.collection_id.choices = [(0, '-- Sem coleção --')] + [(c.id, c.name) for c in user_collections]
    form.supplier_id.choices = [(0, '-- Sem fornecedor --')] + [(s.id, s.name) for s in user_suppliers]

    from app.models.fluxogama_subetapa import FluxogamaSubetapa
    subetapas = FluxogamaSubetapa.query.filter_by(ativo=True, colecao_wsid=None).order_by(FluxogamaSubetapa.nome).all()

    if request.method == 'GET':
        form.stylist.data = user.username
    
    return render_template('upload_batch.html', form=form, current_user=user, subetapas=subetapas)


@specifications_bp.route('/upload_batch_files', methods=['POST'])
@login_required
def upload_batch_files():
    from app.utils.batch_processor import start_batch_processing
    import uuid
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'Sessão inválida'}), 401
    
    files = request.files.getlist('files')
    if not files or len(files) == 0:
        return jsonify({'success': False, 'error': 'Nenhum arquivo enviado'}), 400
    
    collection_id = request.form.get('collection_id', type=int)
    supplier_id = request.form.get('supplier_id', type=int)
    stylist = request.form.get('stylist', user.username)
    price_range = request.form.get('price_range', '')
    fluxogama_subetapa = request.form.get('fluxogama_subetapa', '').strip() or None
    
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    
    allowed_extensions = {'pdf', 'jpg', 'jpeg', 'png'}
    created_specs = []
    errors = []
    
    for file in files:
        if not file or not file.filename:
            continue
        
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            errors.append(f"{file.filename}: formato não suportado")
            continue
        
        try:
            filename = secure_filename(file.filename)
            
            base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            unique_filename = f"{base_name}_{uuid.uuid4().hex[:6]}.{ext}"
            
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            spec = Specification()
            spec.user_id = user.id
            spec.pdf_filename = unique_filename
            spec.collection_id = collection_id if collection_id and collection_id != 0 else None
            spec.batch_id = batch_id
            spec.processing_status = 'pending'
            spec.processing_stage = 0
            spec.stylists = stylist
            spec.price_range = price_range if price_range else None
            spec.fluxogama_subetapa = fluxogama_subetapa
            spec.created_at = datetime.now()
            spec.set_status('in_development')
            
            if supplier_id and supplier_id != 0:
                spec.supplier_id = supplier_id
                selected_supplier = Supplier.query.get(supplier_id)
                spec.supplier = selected_supplier.name if selected_supplier else None
            
            db.session.add(spec)
            db.session.commit()
            
            created_specs.append({
                'id': spec.id,
                'filename': unique_filename,
                'original_filename': file.filename
            })
            
            log_activity('BATCH_UPLOAD', 'specification', spec.id,
                        target_name=unique_filename,
                        metadata={'batch_id': batch_id, 'original_filename': file.filename})
            
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
            db.session.rollback()
    
    if created_specs:
        app = current_app._get_current_object()
        start_batch_processing(batch_id, current_app.config['UPLOAD_FOLDER'], app, batch_size=5)
        rpa_info(f"BATCH_UPLOAD: Lote {batch_id} iniciado com {len(created_specs)} arquivos")
    
    return jsonify({
        'success': True,
        'batch_id': batch_id,
        'total_files': len(created_specs),
        'created_specs': created_specs,
        'errors': errors
    })


@specifications_bp.route('/batch_status/<batch_id>')
@login_required
def batch_status(batch_id):
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'Sessão inválida'}), 401
    
    if user.is_admin:
        specs = Specification.query.filter_by(batch_id=batch_id).all()
    else:
        specs = Specification.query.filter_by(batch_id=batch_id, user_id=user.id).all()
    
    if not specs:
        return jsonify({'success': False, 'error': 'Lote não encontrado'}), 404
    
    total = len(specs)
    completed = sum(1 for s in specs if s.processing_status == 'completed')
    processing = sum(1 for s in specs if s.processing_status == 'processing')
    pending = sum(1 for s in specs if s.processing_status == 'pending')
    errors = sum(1 for s in specs if s.processing_status == 'error')
    
    stage_map = {
        0: 'pending',
        1: 'thumbnail',
        2: 'extract_image',
        3: 'extract_text',
        4: 'openai_parse',
        5: 'supplier_link',
        6: 'completed'
    }
    
    specs_info = []
    for s in specs:
        stage_num = s.processing_stage or 0
        processing_stage = stage_map.get(stage_num, 'processing')
        if s.processing_status == 'error':
            processing_stage = 'error'
        elif s.processing_status == 'completed':
            processing_stage = 'completed'
        
        specs_info.append({
            'id': s.id,
            'filename': s.pdf_filename,
            'status': s.processing_status,
            'stage': stage_num,
            'processing_stage': processing_stage,
            'stage_name': {
                0: 'Aguardando',
                1: 'Thumbnail',
                2: 'Extraindo Imagem',
                3: 'Extraindo Texto',
                4: 'Processando IA',
                5: 'Vinculando Fornecedor',
                6: 'Concluído'
            }.get(stage_num, 'Desconhecido'),
            'error': s.last_error,
            'description': s.description
        })
    
    return jsonify({
        'success': True,
        'batch_id': batch_id,
        'total': total,
        'completed': completed,
        'processing': processing,
        'pending': pending,
        'errors': errors,
        'progress_percent': round((completed / total) * 100) if total > 0 else 0,
        'is_complete': completed + errors == total,
        'specs': specs_info
    })


@specifications_bp.route('/retry_spec/<int:spec_id>', methods=['POST'])
@login_required
def retry_spec(spec_id):
    from app.utils.batch_processor import advance_spec_processing
    import threading
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'Sessão inválida'}), 401
    
    spec = Specification.query.get_or_404(spec_id)
    
    if not user.is_admin and spec.user_id != user.id:
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403
    
    if spec.processing_status != 'error':
        return jsonify({'success': False, 'error': 'Apenas arquivos com erro podem ser reprocessados'}), 400
    
    spec.processing_status = 'pending'
    spec.last_error = None
    db.session.commit()
    
    app = current_app._get_current_object()
    upload_folder = current_app.config['UPLOAD_FOLDER']
    
    def retry_in_background():
        with app.app_context():
            advance_spec_processing(spec_id, upload_folder, app)
    
    thread = threading.Thread(target=retry_in_background, daemon=True)
    thread.start()
    
    return jsonify({
        'success': True,
        'message': 'Reprocessamento iniciado',
        'spec_id': spec_id
    })
