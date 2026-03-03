import json
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from app.extensions import db
from app.models import User, FichaTecnica, FichaTecnicaItem
from app.utils.auth import login_required
from app.utils.excel_parser import clean_string, parse_number, NUMERIC_FIELDS

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


@fichas_bp.route('/<int:ficha_id>/itens/<int:item_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_item(ficha_id, item_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        session.clear()
        flash('Sessao invalida. Por favor, faca login novamente.')
        return redirect(url_for('auth.login'))

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not user.is_admin and ficha.user_id != user.id:
        flash('Acesso negado.')
        return redirect(url_for('dashboard.index'))

    item = FichaTecnicaItem.query.get_or_404(item_id)
    if item.ficha_id != ficha.id:
        flash('Item nao pertence a esta ficha.')
        return redirect(url_for('fichas.tabela', ficha_id=ficha.id))

    try:
        columns = json.loads(ficha.columns_meta) if ficha.columns_meta else []
    except (TypeError, ValueError):
        columns = []

    raw_row = {}
    if item.raw_row:
        try:
            raw_row = json.loads(item.raw_row)
        except (TypeError, ValueError):
            raw_row = {}

    model_fields = set(FichaTecnicaItem.__table__.columns.keys())
    model_fields.discard('id')
    model_fields.discard('ficha_id')
    model_fields.discard('created_at')
    model_fields.discard('raw_row')

    if request.method == 'POST':
        for col in columns:
            field_name = col.get('name')
            if not field_name:
                continue
            form_key = f"field_{field_name}"
            if form_key not in request.form:
                continue
            value = request.form.get(form_key)
            if field_name in model_fields:
                if field_name in NUMERIC_FIELDS:
                    setattr(item, field_name, parse_number(value))
                else:
                    setattr(item, field_name, clean_string(value))
            else:
                source_name = col.get('sourceColumnName') or field_name
                raw_row[source_name] = clean_string(value)

        item.raw_row = json.dumps(raw_row)
        db.session.commit()
        flash('Item atualizado com sucesso.')
        return redirect(url_for('fichas.tabela', ficha_id=ficha.id))

    fields = []
    for col in columns:
        field_name = col.get('name')
        if not field_name:
            continue
        label = col.get('sourceColumnName') or field_name
        if field_name in model_fields:
            value = getattr(item, field_name, None)
        else:
            value = raw_row.get(label)
        fields.append({
            'name': field_name,
            'label': label,
            'value': '' if value is None else value,
        })

    return render_template(
        'ficha_tecnica_item_edit.html',
        ficha=ficha,
        item=item,
        fields=fields,
        current_user=user,
    )
