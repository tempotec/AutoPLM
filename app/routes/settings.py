from flask import Blueprint, render_template, redirect, url_for, flash, session
from app.extensions import db
from app.models import User
from app.forms import SettingsForm
from app.utils.auth import login_required

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def index():
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('Sessão inválida. Por favor, faça login novamente.')
        return redirect(url_for('auth.login'))

    form = SettingsForm(obj=user)

    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user and existing_user.id != user.id:
            flash('Este nome de usuário já está em uso.')
            return render_template('settings.html', form=form, user=user)

        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email and existing_email.id != user.id:
            flash('Este e-mail já está em uso.')
            return render_template('settings.html', form=form, user=user)

        user.username = form.username.data
        user.email = form.email.data

        try:
            db.session.commit()
            flash('Suas informações foram atualizadas com sucesso!')
            return redirect(url_for('settings.index'))
        except Exception as e:
            db.session.rollback()
            flash('Erro ao atualizar suas informações. Tente novamente.')
            print(f"Error updating user: {e}")

    return render_template('settings.html', form=form, user=user)
