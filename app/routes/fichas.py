from flask import Blueprint, render_template, session, redirect, url_for, flash
from app.models import User, FichaTecnica
from app.utils.auth import login_required

fichas_bp = Blueprint('fichas', __name__, url_prefix='/fichas')


@fichas_bp.route('/import', methods=['GET'])
@login_required
def import_view():
    user = User.query.get(session.get('user_id'))
    if not user:
        session.clear()
        flash('Sessao invalida. Por favor, faca login novamente.')
        return redirect(url_for('auth.login'))
    return render_template('ficha_tecnica_import.html', current_user=user)


@fichas_bp.route('/<int:ficha_id>/tabela', methods=['GET'])
@login_required
def tabela(ficha_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        session.clear()
        flash('Sessao invalida. Por favor, faca login novamente.')
        return redirect(url_for('auth.login'))

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not user.is_admin and ficha.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    return render_template('ficha_tecnica_table.html', ficha=ficha, current_user=user)
