import os
from flask import Blueprint, render_template, redirect, url_for, flash, session, request, current_app
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import User, Collection, Specification
from app.utils.auth import login_required
from app.utils.logging import log_activity, rpa_info, rpa_error

collections_bp = Blueprint('collections', __name__)


@collections_bp.route('/collections')
@login_required
def index():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')

    if user.is_admin:
        query = Collection.query
    else:
        query = Collection.query.filter_by(user_id=user.id)

    if search_query:
        query = query.filter(Collection.name.ilike(f'%{search_query}%'))

    if status_filter:
        query = query.filter_by(status=status_filter)

    collections = query.order_by(Collection.created_at.desc()).all()

    collections_with_counts = []
    for collection in collections:
        spec_count = Specification.query.filter_by(collection_id=collection.id).count()
        collections_with_counts.append({
            'collection': collection,
            'spec_count': spec_count
        })

    return render_template('collections.html',
                           current_user=user,
                           collections=collections_with_counts,
                           search_query=search_query,
                           status_filter=status_filter)


@collections_bp.route('/collections/create', methods=['GET', 'POST'])
@login_required
def create():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        status = request.form.get('status', 'em_desenvolvimento')

        if not name:
            flash('Nome da coleção é obrigatório.')
            return redirect(url_for('collections.create'))

        try:
            collection = Collection()
            collection.user_id = user.id
            collection.name = name
            collection.description = description
            collection.status = status

            cover_file = request.files.get('cover_image')
            if cover_file and cover_file.filename:
                filename = secure_filename(cover_file.filename)
                covers_dir = os.path.join(current_app.static_folder, 'covers')
                os.makedirs(covers_dir, exist_ok=True)
                cover_path = os.path.join(covers_dir, filename)
                cover_file.save(cover_path)
                collection.cover_image = f'/static/covers/{filename}'

            db.session.add(collection)
            db.session.commit()

            log_activity('CREATE_COLLECTION', 'collection', collection.id, target_name=collection.name)
            rpa_info(f"CREATE_COLLECTION: Coleção '{collection.name}' criada (ID: {collection.id})")
            flash('Coleção criada com sucesso!')
            return redirect(url_for('collections.index'))
        except Exception as e:
            db.session.rollback()
            rpa_error(f"CREATE_COLLECTION_ERRO: Erro ao criar coleção", exc=e, regiao="colecoes")
            flash('Erro ao criar coleção.')
            print(f"Error creating collection: {e}")

    return render_template('create_collection.html', current_user=user)


@collections_bp.route('/collections/<int:id>')
@login_required
def view(id):
    collection = Collection.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user.is_admin and collection.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('collections.index'))

    specifications = Specification.query.filter_by(collection_id=collection.id).order_by(
        Specification.created_at.desc()).all()

    log_activity('VIEW_COLLECTION', 'collection', collection.id, target_name=collection.name)

    return render_template('view_collection.html',
                           current_user=user,
                           collection=collection,
                           specifications=specifications)


@collections_bp.route('/collections/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit(id):
    collection = Collection.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user.is_admin and collection.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('collections.index'))

    if request.method == 'POST':
        collection.name = request.form.get('name', collection.name)
        collection.description = request.form.get('description', collection.description)
        collection.status = request.form.get('status', collection.status)

        cover_file = request.files.get('cover_image')
        if cover_file and cover_file.filename:
            filename = secure_filename(cover_file.filename)
            covers_dir = os.path.join(current_app.static_folder, 'covers')
            os.makedirs(covers_dir, exist_ok=True)
            cover_path = os.path.join(covers_dir, filename)
            cover_file.save(cover_path)
            collection.cover_image = f'/static/covers/{filename}'

        try:
            db.session.commit()
            log_activity('EDIT_COLLECTION', 'collection', collection.id, target_name=collection.name)
            rpa_info(f"EDIT_COLLECTION: Coleção '{collection.name}' atualizada (ID: {collection.id})")
            flash('Coleção atualizada com sucesso!')
            return redirect(url_for('collections.view', id=collection.id))
        except Exception as e:
            db.session.rollback()
            rpa_error(f"EDIT_COLLECTION_ERRO: Erro ao atualizar coleção", exc=e, regiao="colecoes")
            flash('Erro ao atualizar coleção.')
            print(f"Error updating collection: {e}")

    return render_template('edit_collection.html', current_user=user, collection=collection)


@collections_bp.route('/collections/<int:id>/delete', methods=['POST'])
@login_required
def delete(id):
    collection = Collection.query.get_or_404(id)
    user = User.query.get(session['user_id'])

    if not user.is_admin and collection.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('collections.index'))

    try:
        collection_name = collection.name
        db.session.delete(collection)
        db.session.commit()
        log_activity('DELETE_COLLECTION', 'collection', id, target_name=collection_name)
        rpa_info(f"DELETE_COLLECTION: Coleção '{collection_name}' excluída (ID: {id})")
        flash('Coleção excluída com sucesso!')
    except Exception as e:
        db.session.rollback()
        rpa_error(f"DELETE_COLLECTION_ERRO: Erro ao excluir coleção ID {id}", exc=e, regiao="colecoes")
        flash('Erro ao excluir coleção.')
        print(f"Error deleting collection: {e}")

    return redirect(url_for('collections.index'))
