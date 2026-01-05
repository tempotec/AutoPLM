import os
import io
import base64
import uuid
import threading
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, jsonify, send_file, current_app
try:
    from replit.object_storage import Client
except ImportError:
    Client = None
from app.extensions import db, get_openai_client
from app.models import User, Specification, Collection
from app.utils.auth import login_required, admin_required
from app.utils.files import is_image_file, is_pdf_file, convert_image_to_base64
from app.utils.pdf import extract_images_from_pdf, generate_image_thumbnail, generate_pdf_thumbnail
from app.utils.ai import analyze_images_with_gpt4_vision, build_technical_drawing_prompt
from app.utils.logging import log_activity, rpa_info, rpa_error

drawings_bp = Blueprint('drawings', __name__)


def generate_drawing_background(spec_id, file_path, app):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=db.engine)
    thread_session = Session()
    
    try:
        spec = thread_session.query(Specification).get(spec_id)
        if not spec:
            print(f"Specification {spec_id} not found")
            thread_session.close()
            return
        
        spec.processing_status = 'processing'
        thread_session.commit()
        
        openai_client = get_openai_client()
        if not openai_client:
            print("OpenAI client not initialized")
            spec.processing_status = 'error'
            thread_session.commit()
            thread_session.close()
            return
        
        base_image_bytes = None

        if is_image_file(spec.pdf_filename):
            print(f"📸 Arquivo de imagem detectado para edição: {spec.pdf_filename}")
            with open(file_path, "rb") as f:
                base_image_bytes = f.read()

        elif is_pdf_file(spec.pdf_filename):
            print(f"📄 Arquivo PDF detectado para edição: {spec.pdf_filename}")
            pdf_images_data = extract_images_from_pdf(file_path)
            if pdf_images_data:
                largest_img = max(pdf_images_data, key=lambda x: x.get('area', 0))
                print(f"✓ Usando imagem da página {largest_img['page']} como base para edição")
                base_image_bytes = base64.b64decode(largest_img['base64'])
            else:
                print("⚠️ Nenhuma imagem encontrada no PDF para servir de base")
        else:
            print(f"Formato de arquivo não suportado: {spec.pdf_filename}")

        if not base_image_bytes:
            print("⚠️ Sem imagem base — voltando para geração pura (sem edição).")
            
            images = []
            if is_image_file(spec.pdf_filename):
                image_b64 = convert_image_to_base64(file_path)
                if image_b64:
                    images = [image_b64]
            elif is_pdf_file(spec.pdf_filename):
                pdf_images_data = extract_images_from_pdf(file_path)
                images = [img['base64'] for img in pdf_images_data] if pdf_images_data else []

            visual_desc = analyze_images_with_gpt4_vision(images) if images else None
            prompt = build_technical_drawing_prompt(spec, visual_desc)

            response = openai_client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024",
                quality="high",
                n=1
            )
        else:
            images_b64 = []
            if is_image_file(spec.pdf_filename):
                img_b64 = convert_image_to_base64(file_path)
                if img_b64:
                    images_b64 = [img_b64]
            elif is_pdf_file(spec.pdf_filename):
                pdf_images_data = extract_images_from_pdf(file_path)
                images_b64 = [img['base64'] for img in pdf_images_data] if pdf_images_data else []

            visual_desc = analyze_images_with_gpt4_vision(images_b64) if images_b64 else None
            prompt = build_technical_drawing_prompt(spec, visual_desc)

            base_image_file = io.BytesIO(base_image_bytes)
            base_image_file.name = "base.png"

            print("🧠 Chamando gpt-image-1 em modo EDIÇÃO (images.edit) com imagem base...")
            response = openai_client.images.edit(
                model="gpt-image-1",
                image=base_image_file,
                prompt=prompt,
                size="1024x1024",
                quality="high",
                n=1
            )

        b64_json = response.data[0].b64_json
        if b64_json:
            image_data = base64.b64decode(b64_json)
        else:
            raise ValueError("No b64_json in response")
        drawing_filename = f"drawing_{spec.id}_{uuid.uuid4().hex[:8]}.png"
        
        static_drawings_dir = os.path.join('static', 'drawings')
        os.makedirs(static_drawings_dir, exist_ok=True)
        static_drawing_path = os.path.join(static_drawings_dir, drawing_filename)
        
        with open(static_drawing_path, 'wb') as f:
            f.write(image_data)
        
        spec.technical_drawing_url = f"/static/drawings/{drawing_filename}"
        print(f"✅ Desenho técnico salvo em: {spec.technical_drawing_url}")

        spec.processing_status = 'completed'
        thread_session.commit()
        thread_session.close()
        print(f"✅ Desenho técnico gerado com sucesso para spec {spec_id} (agora image-to-image)")

    except Exception as e:
        print(f"❌ Error generating technical drawing for spec {spec_id}: {e}")
        import traceback
        traceback.print_exc()
        try:
            spec_obj = thread_session.query(Specification).get(spec_id)
            if spec_obj:
                spec_obj.processing_status = 'error'
                thread_session.commit()
        except Exception as update_error:
            print(f"Error updating specification status: {update_error}")
        finally:
            thread_session.close()


@drawings_bp.route('/specification/<int:id>/generate_drawing', methods=['POST'])
@login_required
def generate(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return jsonify({'success': False, 'error': 'Sessão inválida'}), 401

    if not user.is_admin and spec.user_id != user.id:
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    openai_client = get_openai_client()
    if not openai_client:
        return jsonify({
            'success': False,
            'error': 'OpenAI não configurado'
        }), 500

    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename)

        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': 'Arquivo não encontrado'
            }), 404

        spec.processing_status = 'processing'
        db.session.commit()

        spec_id = spec.id
        
        log_activity('GENERATE_DRAWING', 'specification', spec_id,
                    target_name=spec.description or spec.ref_souq)
        rpa_info(f"DESENHO_TECNICO: Iniciando geração para spec ID {spec_id} por '{user.username}'")

        from flask import current_app as flask_app
        app = flask_app._get_current_object()  # type: ignore

        def process_in_background():
            with app.app_context():
                try:
                    generate_drawing_background(spec_id, file_path, app)
                    rpa_info(f"DESENHO_TECNICO: Geração concluída para spec ID {spec_id}")
                except Exception as e:
                    print(f"❌ Error in background drawing generation thread: {e}")
                    import traceback
                    traceback.print_exc()
                    rpa_error(f"DESENHO_TECNICO_ERRO: Falha ao gerar desenho para spec ID {spec_id}", exc=e, regiao="geracao_desenho")
                    try:
                        from sqlalchemy.orm import sessionmaker
                        Session = sessionmaker(bind=db.engine)
                        error_session = Session()
                        error_spec = error_session.query(Specification).get(spec_id)
                        if error_spec:
                            error_spec.processing_status = 'error'
                            error_session.commit()
                        error_session.close()
                    except:
                        pass

        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'message': 'Geração de desenho técnico iniciada! Processamento em segundo plano.',
            'spec_id': spec_id
        })

    except Exception as e:
        print(f"Error in generate_technical_drawing: {e}")
        import traceback
        traceback.print_exc()
        rpa_error(f"DESENHO_TECNICO_ERRO: Erro ao iniciar geração de desenho", exc=e, regiao="geracao_desenho")
        return jsonify({
            'success': False,
            'error': 'Erro ao iniciar geração de desenho'
        }), 500


@drawings_bp.route('/specification/<int:id>/download_drawing', methods=['GET'])
@login_required
def download(id):
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

        if not spec.technical_drawing_url:
            flash('Esta especificação não possui desenho técnico.')
            return redirect(url_for('specifications.view', id=id))

        ref_name = spec.ref_souq or spec.description or f"spec_{id}"
        ref_name = "".join(c if c.isalnum() or c in ['-', '_'] else '_' for c in ref_name)
        download_filename = f"desenho_tecnico_{ref_name}.png"

        if spec.technical_drawing_url.startswith('/static/'):
            local_path = spec.technical_drawing_url.lstrip('/')
            if os.path.exists(local_path):
                log_activity('DOWNLOAD_DRAWING', 'specification', spec.id, target_name=spec.description or spec.ref_souq)
                rpa_info(f"DOWNLOAD_DRAWING: Desenho técnico baixado (ID: {spec.id})")
                return send_file(local_path,
                               mimetype='image/png',
                               as_attachment=True,
                               download_name=download_filename)

        if spec.technical_drawing_url.startswith('http://') or spec.technical_drawing_url.startswith('https://'):
            return redirect(spec.technical_drawing_url)
        
        if Client:
            try:
                storage_client = Client()
                if storage_client.exists(spec.technical_drawing_url):
                    image_data = storage_client.download_as_bytes(spec.technical_drawing_url)
                    return send_file(io.BytesIO(image_data),
                                   mimetype='image/png',
                                   as_attachment=True,
                                   download_name=download_filename)
            except Exception as storage_error:
                print(f"Object Storage lookup failed: {storage_error}")

        drawing_path = os.path.join(current_app.config['UPLOAD_FOLDER'], spec.technical_drawing_url)
        if os.path.exists(drawing_path):
            return send_file(drawing_path, 
                           mimetype='image/png',
                           as_attachment=True,
                           download_name=download_filename)
        else:
            flash('Arquivo de desenho não encontrado.')
            return redirect(url_for('specifications.view', id=id))
            
    except Exception as e:
        print(f"Error downloading drawing: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao baixar desenho técnico.')
        return redirect(url_for('specifications.view', id=id))


@drawings_bp.route('/specification/<int:id>/view_drawing', methods=['GET'])
@login_required
def view_drawing(id):
    spec = Specification.query.get_or_404(id)
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('SessÇœo invÇ­lida. Por favor, faÇõa login novamente.')
        return redirect(url_for('auth.login'))

    if not user.is_admin and spec.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    if not spec.technical_drawing_url:
        flash('Esta especificaÇõÇœo nÇœo possui desenho tÇ¸cnico.')
        return redirect(url_for('specifications.view', id=id))

    drawing_url = spec.technical_drawing_url

    if drawing_url.startswith('/static/'):
        return redirect(drawing_url)

    if drawing_url.startswith('http://') or drawing_url.startswith('https://'):
        return redirect(drawing_url)

    if Client:
        try:
            storage_client = Client()
            if storage_client.exists(drawing_url):
                image_data = storage_client.download_as_bytes(drawing_url)
                return send_file(io.BytesIO(image_data), mimetype='image/png', as_attachment=False)
        except Exception as storage_error:
            print(f"Object Storage lookup failed: {storage_error}")

    drawing_path = os.path.join(current_app.config['UPLOAD_FOLDER'], drawing_url)
    if os.path.exists(drawing_path):
        ext = drawing_url.lower().rsplit('.', 1)[-1]
        mimetype_map = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png'
        }
        mimetype = mimetype_map.get(ext, 'image/png')
        return send_file(drawing_path, mimetype=mimetype, as_attachment=False)

    flash('Arquivo de desenho nÇœo encontrado.')
    return redirect(url_for('specifications.view', id=id))


@drawings_bp.route('/technical-drawings')
@login_required
def gallery():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    page = request.args.get('page', 1, type=int)
    per_page = 12

    if user.is_admin:
        query = Specification.query.filter(Specification.technical_drawing_url.isnot(None))
    else:
        query = Specification.query.filter(
            Specification.user_id == user.id,
            Specification.technical_drawing_url.isnot(None))

    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(
            db.or_(Specification.description.ilike(f'%{search}%'),
                   Specification.ref_souq.ilike(f'%{search}%'),
                   Specification.collection.ilike(f'%{search}%')))

    collection_filter = request.args.get('collection', '').strip()
    if collection_filter:
        query = query.filter(Specification.collection_id == collection_filter)

    supplier_filter = request.args.get('supplier', '').strip()
    if supplier_filter:
        query = query.filter(Specification.supplier.ilike(f'%{supplier_filter}%'))

    if user.is_admin:
        all_collections = Collection.query.order_by(Collection.name).all()
    else:
        all_collections = Collection.query.filter_by(user_id=user.id).order_by(Collection.name).all()

    if user.is_admin:
        suppliers_query = db.session.query(Specification.supplier).filter(
            Specification.supplier.isnot(None), Specification.supplier != '',
            Specification.technical_drawing_url.isnot(None)).distinct().order_by(Specification.supplier)
    else:
        suppliers_query = db.session.query(Specification.supplier).filter(
            Specification.user_id == user.id,
            Specification.supplier.isnot(None), Specification.supplier != '',
            Specification.technical_drawing_url.isnot(None)).distinct().order_by(Specification.supplier)

    all_suppliers = [s[0] for s in suppliers_query.all()]

    pagination = query.order_by(Specification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    return render_template('technical_drawings.html',
                           current_user=user,
                           specifications=pagination.items,
                           pagination=pagination,
                           collections=all_collections,
                           suppliers=all_suppliers,
                           search=search,
                           selected_collection=collection_filter,
                           selected_supplier=supplier_filter)


@drawings_bp.route('/admin/generate_thumbnails', methods=['GET'])
@admin_required
def generate_all_thumbnails():
    try:
        specs = Specification.query.filter(Specification.pdf_thumbnail.is_(None)).all()

        if not specs:
            flash('Todas as fichas já têm thumbnails!')
            return redirect(url_for('dashboard.index'))

        processed = 0
        errors = 0

        for spec in specs:
            try:
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], spec.pdf_filename)

                if not os.path.exists(file_path):
                    print(f"Arquivo não encontrado: {file_path}")
                    errors += 1
                    continue

                if is_image_file(spec.pdf_filename):
                    thumbnail_url = generate_image_thumbnail(file_path, spec.id)
                else:
                    thumbnail_url = generate_pdf_thumbnail(file_path, spec.id)

                if thumbnail_url:
                    spec.pdf_thumbnail = thumbnail_url
                    db.session.commit()
                    processed += 1
                    print(f"✓ Thumbnail gerado para spec #{spec.id}: {thumbnail_url}")
                else:
                    errors += 1
                    print(f"✗ Erro ao gerar thumbnail para spec #{spec.id}")

            except Exception as e:
                errors += 1
                print(f"✗ Erro ao processar spec #{spec.id}: {e}")
                continue

        if processed > 0:
            flash(f'✓ {processed} thumbnails gerados com sucesso! ({errors} erros)')
        else:
            flash(f'Nenhum thumbnail foi gerado. ({errors} erros)')

    except Exception as e:
        flash(f'Erro ao gerar thumbnails: {str(e)}')
        print(f"Erro ao gerar thumbnails: {e}")
        import traceback
        traceback.print_exc()

    return redirect(url_for('dashboard.index'))


@drawings_bp.route('/admin/activity-logs')
@admin_required
def activity_logs():
    from app.models import ActivityLog
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    search_query = request.args.get('search', '').strip()
    action_filter = request.args.get('action', '').strip()
    user_filter = request.args.get('user', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    
    query = ActivityLog.query
    
    if search_query:
        query = query.filter(
            db.or_(
                ActivityLog.username.ilike(f'%{search_query}%'),
                ActivityLog.target_name.ilike(f'%{search_query}%'),
                ActivityLog.action.ilike(f'%{search_query}%')
            )
        )
    
    if action_filter:
        query = query.filter(ActivityLog.action == action_filter)
    
    if user_filter:
        query = query.filter(ActivityLog.username.ilike(f'%{user_filter}%'))
    
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(ActivityLog.created_at >= from_date)
        except ValueError:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            to_date = to_date.replace(hour=23, minute=59, second=59)
            query = query.filter(ActivityLog.created_at <= to_date)
        except ValueError:
            pass
    
    all_actions = db.session.query(ActivityLog.action).distinct().order_by(ActivityLog.action).all()
    actions_list = [a[0] for a in all_actions]
    
    all_users = db.session.query(ActivityLog.username).distinct().order_by(ActivityLog.username).all()
    users_list = [u[0] for u in all_users if u[0]]
    
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    
    return render_template('activity_logs.html',
                          current_user=user,
                          logs=pagination.items,
                          pagination=pagination,
                          actions_list=actions_list,
                          users_list=users_list,
                          search_query=search_query,
                          action_filter=action_filter,
                          user_filter=user_filter,
                          date_from=date_from,
                          date_to=date_to)
