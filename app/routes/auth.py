from flask import Blueprint, render_template, redirect, url_for, flash, session
from app.forms import LoginForm
from app.models import User
from app.utils.logging import log_activity, rpa_info, rpa_warn

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            log_activity('LOGIN', user_id=user.id, username=user.username)
            rpa_info(f"LOGIN: Usuário '{user.username}' autenticado com sucesso")
            flash('Login successful!')
            return redirect(url_for('dashboard.index'))
        log_activity('LOGIN_FAILED', metadata={'attempted_username': form.username.data})
        rpa_warn(f"LOGIN_FAILED: Tentativa de login falhou para usuário '{form.username.data}'")
        flash('Invalid username or password.')
    return render_template('login.html', form=form)


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    username = None
    if user_id:
        user = User.query.get(user_id)
        username = user.username if user else None
        log_activity('LOGOUT', user_id=user_id, username=username)
        rpa_info(f"LOGOUT: Usuário '{username}' desconectado")
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('auth.login'))
