import os
import threading
import re
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from app.extensions import db, get_openai_client
from app.models import User, Specification, Collection, Supplier
from app.forms import UploadPDFForm, SpecificationForm
from app.utils.auth import login_required
from app.utils.files import is_image_file, is_pdf_file, convert_image_to_base64
from app.utils.pdf import extract_text_from_pdf, extract_images_from_pdf, generate_pdf_thumbnail, generate_image_thumbnail
from app.utils.ai import analyze_images_with_gpt4_vision, process_specification_with_openai
from app.utils.helpers import convert_value_to_string, get_or_create_supplier
from app.utils.logging import log_activity, rpa_info, rpa_error

specifications_bp = Blueprint('specifications', __name__)


def save_product_image(spec_id, image_b64_or_path, is_b64=True):
    try:
        import uuid
        import base64
        product_image_filename = f"product_{spec_id}_{uuid.uuid4().hex[:8]}.png"
        product_image_path = os.path.join('static', 'product_images', product_image_filename)
        os.makedirs(os.path.dirname(product_image_path), exist_ok=True)

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

            product_img_url = save_product_image(spec_id, file_path, is_b64=False)
            if product_img_url:
                spec.technical_drawing_url = product_img_url
                print(f"✓ Imagem do produto salva: {product_img_url}")

            print("⚠️ Arquivo de imagem: pulando extração de texto.")
            print("📸 Usando APENAS análise visual GPT-4o para extrair informações.")

            image_b64 = convert_image_to_base64(file_path)
            if not image_b64:
                print("❌ Erro ao converter imagem para base64")
                spec.processing_status = 'error'
                thread_session.commit()
                thread_session.close()
                return

            visual_analysis = analyze_images_with_gpt4_vision([image_b64])

            if not visual_analysis:
                print("❌ Erro na análise visual da imagem")
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

                print(f"✓ Dados extraídos da análise visual (JSON estruturado):")
                print(f"  - Descrição: {spec.description}")
                print(f"  - Categoria: {spec.composition}")
                print(f"  - Grupo: {spec.main_group}")
                print(f"  - Subgrupo: {spec.sub_group}")
            else:
                print("⚠️ Análise visual retornou texto (fallback de JSON)")
                visual_text = str(visual_analysis)
                extracted_data = process_specification_with_openai(visual_text)

                if extracted_data:
                    for key, value in extracted_data.items():
                        if hasattr(spec, key) and value is not None:
                            if key in ['tech_sheet_delivery_date', 'pilot_delivery_date']:
                                if isinstance(value, str):
                                    if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
                                        print(f"  ⚠️ Ignorando data inválida para {key}: {value}")
                                        continue
                            setattr(spec, key, convert_value_to_string(value))

                    supplier_name = extracted_data.get('supplier')
                    if supplier_name and isinstance(supplier_name, str) and supplier_name.strip():
                        print(f"\n📦 Fornecedor detectado na análise: {supplier_name}")
                        supplier = get_or_create_supplier(supplier_name, spec.user_id, thread_session)
                        if supplier:
                            spec.supplier_id = supplier.id
                            spec.supplier = supplier.name
                else:
                    spec.description = "Peça de Vestuário (Imagem)"

            spec.processing_status = 'completed'
            thread_session.commit()
            thread_session.close()
            print(f"✓ Imagem processada com sucesso via análise visual!")
            return

        elif is_pdf_file(filename):
            print(f"\n{'='*80}")
            print(f"PROCESSAMENTO DE PDF DETECTADO: {filename}")
            print(f"{'='*80}\n")

            thumbnail_url = generate_pdf_thumbnail(file_path, spec_id)
            if thumbnail_url:
                spec.pdf_thumbnail = thumbnail_url
                print(f"✓ Thumbnail do PDF gerado: {thumbnail_url}")

            pdf_images = extract_images_from_pdf(file_path)
            if pdf_images and len(pdf_images) > 0:
                largest_img = max(pdf_images, key=lambda x: x.get('area', 0))
                product_img_url = save_product_image(spec_id, largest_img['base64'], is_b64=True)
                if product_img_url:
                    spec.technical_drawing_url = product_img_url
                    print(f"✓ Imagem do produto extraída do PDF e salva: {product_img_url}")

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

    if request.method == 'GET':
        form.stylist.data = user.username

    if request.method == 'POST' and form.validate_on_submit():
        try:
            file = form.pdf_file.data
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
            spec.processing_status = 'processing'
            spec.status = 'draft'
            spec.created_at = datetime.now()

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
                    'spec_id': spec_id
                })

            flash('Arquivo enviado! Processamento iniciado em segundo plano.')
            return redirect(url_for('dashboard.index'))

        except Exception as e:
            db.session.rollback()
            print(f"Error in upload_pdf: {e}")
            import traceback
            traceback.print_exc()
            rpa_error(f"UPLOAD_ERRO: Erro ao fazer upload do arquivo", exc=e, regiao="upload")
            flash('Erro ao processar o arquivo PDF. Por favor, tente novamente ou contate o suporte.')
            return render_template('upload_pdf.html', form=form, current_user=user)

    return render_template('upload_pdf.html', form=form, current_user=user)


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
    return render_template('view_specification.html', specification=spec)


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

    if form.validate_on_submit():
        collection_id = form.collection_id.data if form.collection_id.data and form.collection_id.data != 0 else None
        form.populate_obj(spec)
        spec.collection_id = collection_id
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

    return render_template('edit_specification.html', form=form, specification=spec)


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
        print(f"Erro ao excluir especificação {id}: {e}")
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
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename)
        if os.path.exists(file_path):
            return send_file(file_path, mimetype='application/pdf')
        else:
            flash('Arquivo PDF não encontrado.')
            return redirect(url_for('specifications.view', id=id))
    except Exception as e:
        flash('Erro ao visualizar o arquivo PDF.')
        return redirect(url_for('specifications.view', id=id))


@specifications_bp.route('/view_image/<int:id>')
@login_required
def view_image(id):
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
            ext = spec.pdf_filename.lower().split('.')[-1]
            mimetype_map = {
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png'
            }
            mimetype = mimetype_map.get(ext, 'image/jpeg')
            return send_file(file_path, mimetype=mimetype)
        else:
            flash('Arquivo de imagem não encontrado.')
            return redirect(url_for('specifications.view', id=id))
    except Exception as e:
        flash('Erro ao visualizar o arquivo de imagem.')
        return redirect(url_for('specifications.view', id=id))
