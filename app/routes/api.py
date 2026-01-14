import io
import json
import csv
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, session, request, send_file
from app.extensions import csrf, db
from app.models import User, Specification, FichaTecnica, FichaTecnicaItem
from app.utils.auth import login_required
from app.utils.excel_parser import parse_excel, HEADER_FIELD_MAP
import logging

api_bp = Blueprint('api', __name__, url_prefix='/api')

logger = logging.getLogger('ficha_tecnica_import')

STAGE_MAP = {
    0: 'pending',
    1: 'thumbnail',
    2: 'extract_image',
    3: 'extract_text',
    4: 'openai_parse',
    5: 'supplier_link',
    6: 'completed'
}

_IMPORT_CACHE = {}
_IMPORT_CACHE_TTL = timedelta(minutes=30)


def get_processing_stage(spec):
    stage_num = spec.processing_stage or 0
    if spec.processing_status == 'error':
        return 'error'
    elif spec.processing_status == 'completed':
        return 'completed'
    return STAGE_MAP.get(stage_num, 'processing')


def _cache_import_payload(payload):
    token = str(uuid.uuid4())
    _IMPORT_CACHE[token] = {
        'payload': payload,
        'expires_at': datetime.utcnow() + _IMPORT_CACHE_TTL,
    }
    return token


def _pop_import_payload(token):
    data = _IMPORT_CACHE.get(token)
    if not data:
        return None
    if data['expires_at'] < datetime.utcnow():
        _IMPORT_CACHE.pop(token, None)
        return None
    return _IMPORT_CACHE.pop(token)['payload']


def _prune_import_cache():
    now = datetime.utcnow()
    expired = [k for k, v in _IMPORT_CACHE.items() if v['expires_at'] < now]
    for key in expired:
        _IMPORT_CACHE.pop(key, None)


def _ensure_user_access(user, ficha):
    if not user.is_admin and ficha.user_id != user.id:
        return False
    return True


@api_bp.route('/fichas/import/preview', methods=['POST'])
@login_required
@csrf.exempt
def import_preview():
    _prune_import_cache()

    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Arquivo XLSX nao encontrado'}), 400

    try:
        payload = parse_excel(file.read())
        payload['source_filename'] = file.filename
    except Exception as exc:
        logger.error('Erro ao ler XLSX: %s', exc, exc_info=True)
        return jsonify({'success': False, 'error': f'Falha ao ler o XLSX: {exc}'}), 400

    if payload.get('errors'):
        return jsonify({'success': False, 'error': 'Planilha invalida', 'details': payload['errors']}), 400

    token = _cache_import_payload(payload)
    preview_items = payload['items'][:50]
    return jsonify({
        'success': True,
        'token': token,
        'header': payload.get('header', {}),
        'columns': payload.get('columns', []),
        'counts': {
            'total_items': len(payload.get('items', [])),
            'invalid_rows': len(payload.get('invalid_rows', [])),
        },
        'invalid_rows': payload.get('invalid_rows', []),
        'warnings': payload.get('warnings', []),
        'preview_items': preview_items,
    })


@api_bp.route('/fichas/import/confirm', methods=['POST'])
@login_required
@csrf.exempt
def import_confirm():
    _prune_import_cache()

    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    data = request.get_json(silent=True) or {}
    token = data.get('token')
    if not token:
        return jsonify({'success': False, 'error': 'Token de importacao ausente'}), 400

    payload = _pop_import_payload(token)
    if not payload:
        return jsonify({'success': False, 'error': 'Token expirado ou invalido'}), 400

    header = payload.get('header', {})
    columns = payload.get('columns', [])
    items = payload.get('items', [])

    ficha = FichaTecnica(
        user_id=user.id,
        source_filename=payload.get('source_filename'),
        created_at=datetime.utcnow(),
        header_raw=json.dumps(payload.get('header_raw', [])),
        columns_meta=json.dumps(columns),
        **header
    )
    db.session.add(ficha)
    db.session.flush()

    created = 0
    model_fields = set(FichaTecnicaItem.__table__.columns.keys())
    model_fields.discard('raw_row')
    for item in items:
        clean_payload = {k: v for k, v in item.items() if k in model_fields}
        ficha_item = FichaTecnicaItem(
            ficha_id=ficha.id,
            created_at=datetime.utcnow(),
            raw_row=json.dumps(item.get('raw_row', {})),
            **clean_payload
        )
        db.session.add(ficha_item)
        created += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'ficha_id': ficha.id,
        'created_items': created,
        'skipped_items': len(payload.get('invalid_rows', [])),
    })


@api_bp.route('/fichas', methods=['GET'])
@login_required
def fichas_list():
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    query = FichaTecnica.query
    if not user.is_admin:
        query = query.filter_by(user_id=user.id)
    fichas = query.order_by(FichaTecnica.created_at.desc()).all()

    items = []
    for ficha in fichas:
        items.append({
            'id': ficha.id,
            'number_pi_order': ficha.number_pi_order,
            'supplier_no': ficha.supplier_no,
            'created_at': ficha.created_at.isoformat() if ficha.created_at else None,
            'user_id': ficha.user_id,
        })
    return jsonify({'success': True, 'items': items})


@api_bp.route('/fichas/<int:ficha_id>', methods=['GET'])
@login_required
def ficha_detail(ficha_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    columns = []
    if ficha.columns_meta:
        try:
            columns = json.loads(ficha.columns_meta)
        except (TypeError, ValueError):
            columns = []

    header = {}
    for field in HEADER_FIELD_MAP.values():
        if hasattr(ficha, field):
            header[field] = getattr(ficha, field)

    return jsonify({
        'success': True,
        'id': ficha.id,
        'number_pi_order': ficha.number_pi_order,
        'supplier_no': ficha.supplier_no,
        'created_at': ficha.created_at.isoformat() if ficha.created_at else None,
        'header': header,
        'columns': columns,
    })


@api_bp.route('/fichas/<int:ficha_id>', methods=['DELETE'])
@login_required
@csrf.exempt
def ficha_delete(ficha_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    db.session.delete(ficha)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/fichas/<int:ficha_id>/itens', methods=['GET'])
@login_required
def ficha_itens(ficha_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    page = request.args.get('page', type=int, default=1)
    per_page = request.args.get('per_page', type=int, default=25)
    q = request.args.get('q', type=str, default='').strip()
    sort = request.args.get('sort', type=str, default='item_no_ref_supplier')
    order = request.args.get('order', type=str, default='asc')
    export = request.args.get('export', type=int, default=0)

    query = FichaTecnicaItem.query.filter_by(ficha_id=ficha.id)

    if q:
        query = query.filter(
            FichaTecnicaItem.item_no_ref_supplier.ilike(f"%{q}%")
            | FichaTecnicaItem.oaz_reference.ilike(f"%{q}%")
            | FichaTecnicaItem.description_item.ilike(f"%{q}%")
            | FichaTecnicaItem.nome_desc_produto.ilike(f"%{q}%")
        )

    filters = {
        'grupo': request.args.get('grupo'),
        'linha': request.args.get('linha'),
        'cor': request.args.get('cor'),
    }
    if filters['grupo']:
        query = query.filter(FichaTecnicaItem.grupo.ilike(f"%{filters['grupo']}%"))
    if filters['linha']:
        query = query.filter(FichaTecnicaItem.linha.ilike(f"%{filters['linha']}%"))
    if filters['cor']:
        query = query.filter(
            FichaTecnicaItem.color.ilike(f"%{filters['cor']}%")
            | FichaTecnicaItem.cor_sistema.ilike(f"%{filters['cor']}%")
        )

    sort_column = getattr(FichaTecnicaItem, sort, FichaTecnicaItem.item_no_ref_supplier)
    if order == 'desc':
        sort_column = sort_column.desc()

    query = query.order_by(sort_column)

    if export:
        items = query.all()
        columns = []
        if ficha.columns_meta:
            try:
                columns = json.loads(ficha.columns_meta)
            except (TypeError, ValueError):
                columns = []
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([c['sourceColumnName'] or c['name'] for c in columns])
        for item in items:
            raw = {}
            if item.raw_row:
                try:
                    raw = json.loads(item.raw_row)
                except (TypeError, ValueError):
                    raw = {}
            row = []
            for col in columns:
                if hasattr(item, col['name']):
                    value = getattr(item, col['name'], None)
                else:
                    value = raw.get(col['sourceColumnName'])
                row.append(value)
            writer.writerow(row)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"ficha_{ficha.id}_itens.csv",
        )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    items = []
    if ficha.columns_meta:
        try:
            columns = json.loads(ficha.columns_meta)
        except (TypeError, ValueError):
            columns = []
    else:
        columns = []

    for item in pagination.items:
        raw = {}
        if item.raw_row:
            try:
                raw = json.loads(item.raw_row)
            except (TypeError, ValueError):
                raw = {}
        item_data = {'id': item.id}
        for col in columns:
            if hasattr(item, col['name']):
                item_data[col['name']] = getattr(item, col['name'], None)
            else:
                item_data[col['name']] = raw.get(col['sourceColumnName'])
        items.append(item_data)

    return jsonify({
        'success': True,
        'items': items,
        'page': page,
        'per_page': per_page,
        'total': pagination.total,
    })


@api_bp.route('/fichas/<int:ficha_id>/itens/clear', methods=['POST'])
@login_required
@csrf.exempt
def ficha_itens_clear(ficha_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    deleted = FichaTecnicaItem.query.filter_by(ficha_id=ficha.id).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'deleted': deleted})


@api_bp.route('/fichas/<int:ficha_id>/itens/bulk-delete', methods=['POST'])
@login_required
@csrf.exempt
def ficha_itens_bulk_delete(ficha_id):
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list) or not ids:
        return jsonify({'success': False, 'error': 'Lista de IDs vazia ou invalida'}), 400

    try:
        item_ids = [int(i) for i in ids]
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'IDs invalidos'}), 400

    deleted = (
        FichaTecnicaItem.query
        .filter(FichaTecnicaItem.ficha_id == ficha.id)
        .filter(FichaTecnicaItem.id.in_(item_ids))
        .delete(synchronize_session=False)
    )
    db.session.commit()
    return jsonify({'success': True, 'deleted': deleted})


@api_bp.route('/spec/status/<int:spec_id>', methods=['GET'])
@api_bp.route('/spec_status/<int:spec_id>', methods=['GET'])
@login_required
def get_spec_status(spec_id):
    try:
        spec = Specification.query.get(spec_id)
        if not spec:
            return jsonify({
                'success': False,
                'error': 'Ficha não encontrada'
            }), 404

        user = User.query.get(session['user_id'])
        if not user.is_admin and spec.user_id != user.id:
            return jsonify({'success': False, 'error': 'Acesso negado'}), 403

        return jsonify({
            'success': True,
            'spec_id': spec.id,
            'status': spec.processing_status,
            'processing_stage': get_processing_stage(spec),
            'stage': spec.processing_stage or 0,
            'description': spec.description or 'Processando...',
            'ref_souq': spec.ref_souq or '',
            'has_drawing': bool(spec.technical_drawing_url),
            'error': spec.last_error
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
