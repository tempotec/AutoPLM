from flask import Blueprint, render_template, redirect, url_for, flash, session, request
from app.extensions import db
from app.models import User, Specification
from app.forms import CreateUserForm
from app.utils.auth import admin_required

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/manage_users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)


@admin_bp.route('/create_user', methods=['GET', 'POST'])
@admin_required
def create_user():
    form = CreateUserForm()
    if form.validate_on_submit():
        user = User()
        user.username = form.username.data
        user.email = form.email.data
        user.role = form.role.data
        user.is_admin = (form.role.data == 'admin')
        user.set_password(form.password.data)

        try:
            db.session.add(user)
            db.session.commit()
            flash(f'Usuário {user.username} criado com sucesso!')
            return redirect(url_for('admin.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao criar usuário. Verifique se o nome de usuário e email são únicos.')

    return render_template('create_user.html', form=form)


@admin_bp.route('/user/<int:id>/view')
@admin_required
def view_user(id):
    user_to_view = User.query.get_or_404(id)

    specifications = Specification.query.filter_by(user_id=user_to_view.id).order_by(
        Specification.created_at.desc()).all()

    collections = db.session.query(Specification.collection).distinct().filter(
        Specification.collection.isnot(None),
        Specification.user_id == user_to_view.id).all()
    collections = [c[0] for c in collections if c[0]]

    status_counts = {
        'Draft': Specification.query.filter_by(user_id=user_to_view.id, status='Draft').count(),
        'In Development': Specification.query.filter_by(user_id=user_to_view.id, status='In Development').count(),
        'Approved': Specification.query.filter_by(user_id=user_to_view.id, status='Approved').count(),
        'In Production': Specification.query.filter_by(user_id=user_to_view.id, status='In Production').count(),
    }

    current_user = User.query.get(session['user_id'])

    return render_template('view_user.html',
                           current_user=current_user,
                           user_to_view=user_to_view,
                           specifications=specifications,
                           collections=collections,
                           status_counts=status_counts)


@admin_bp.route('/user/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(id):
    user_to_edit = User.query.get_or_404(id)
    current_user = User.query.get(session['user_id'])

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        role = request.form.get('role')
        new_password = request.form.get('password')

        if not username or not email or not role:
            flash('Todos os campos obrigatórios devem ser preenchidos.')
            return redirect(url_for('admin.edit_user', id=id))

        if username != user_to_edit.username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Nome de usuário já existe. Escolha outro.')
                return redirect(url_for('admin.edit_user', id=id))

        if email != user_to_edit.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('E-mail já está em uso. Escolha outro.')
                return redirect(url_for('admin.edit_user', id=id))

        try:
            user_to_edit.username = username
            user_to_edit.email = email
            user_to_edit.role = role
            user_to_edit.is_admin = (role == 'admin')

            if new_password:
                user_to_edit.set_password(new_password)

            db.session.commit()
            flash(f'Usuário {user_to_edit.username} atualizado com sucesso!')
            return redirect(url_for('admin.manage_users'))
        except Exception as e:
            db.session.rollback()
            print(f"Error updating user: {e}")
            flash('Erro ao atualizar usuário. Tente novamente.')
            return redirect(url_for('admin.edit_user', id=id))

    return render_template('edit_user.html',
                           current_user=current_user,
                           user_to_edit=user_to_edit)


@admin_bp.route('/user/<int:id>/delete', methods=['POST'])
@admin_required
def delete_user(id):
    user_to_delete = User.query.get_or_404(id)
    current_user = User.query.get(session['user_id'])
    
    if user_to_delete.id == current_user.id:
        flash('Você não pode excluir sua própria conta.')
        return redirect(url_for('admin.manage_users'))
    
    try:
        username = user_to_delete.username
        db.session.delete(user_to_delete)
        db.session.commit()
        flash(f'Usuário {username} excluído com sucesso!')
    except Exception as e:
        db.session.rollback()
        flash('Erro ao excluir usuário.')
    
    return redirect(url_for('admin.manage_users'))
