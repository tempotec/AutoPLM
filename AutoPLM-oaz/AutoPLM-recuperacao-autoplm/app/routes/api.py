import io
import json
import csv
import time
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, session, request, send_file
from app.extensions import csrf, db
from app.models import User, Specification, FichaTecnica, FichaTecnicaItem, OazValueMap
from app.utils.auth import login_required
from app.utils.excel_parser import parse_excel, HEADER_FIELD_MAP
from app.utils.compras_parser import parse_compras_xlsx
from app.integrations.oaz.client import OazClient, OazConfigError, compute_payload_hash
from app.integrations.oaz.mapper import (
    build_oaz_payload, get_oaz_map_lookup, normalize_text, FIELD_MAP, DB_FIELDS,
)
from app.integrations.oaz.validator import validate_oaz_payload
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
    6: 'fluxogama_link',
    7: 'completed'
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
        'counts': payload.get('counts_summary', {
            'valid': len(payload.get('items', [])),
            'invalid': len(payload.get('invalid_rows', [])),
            'duplicated_refs': 0,
            'fractional_qty': 0,
        }),
        'invalid_rows': payload.get('invalid_rows', [])[:10],
        'warnings': payload.get('warnings', []),
        'messages': payload.get('messages', []),
        'detected_columns': payload.get('detected_columns', []),
        'missing_columns': payload.get('missing_columns', []),
        'unmapped_columns': payload.get('unmapped_columns', []),
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


# ═══════════════════════════════════════════════════════════════════════
# Compras (Purchased Products) Import → Specifications
# ═══════════════════════════════════════════════════════════════════════

@api_bp.route('/compras/import/preview', methods=['POST'])
@login_required
@csrf.exempt
def compras_import_preview():
    """Upload a Compras XLSX, parse it, return preview of items."""
    _prune_import_cache()

    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Arquivo XLSX nao encontrado'}), 400

    sheet_name = request.form.get('sheet_name', '').strip() or None

    try:
        file_bytes = file.read()
        result = parse_compras_xlsx(file_bytes, sheet_name=sheet_name)
    except Exception as exc:
        logger.error('Erro ao ler XLSX compras: %s', exc, exc_info=True)
        return jsonify({'success': False, 'error': f'Falha ao ler o XLSX: {exc}'}), 400

    if result.get('errors'):
        return jsonify({
            'success': False,
            'error': '; '.join(result['errors']),
            'sheet_names': result.get('sheet_names', []),
        }), 400

    # Cache for confirm step
    result['source_filename'] = file.filename
    token = _cache_import_payload(result)

    return jsonify({
        'success': True,
        'token': token,
        'sheet_names': result.get('sheet_names', []),
        'selected_sheet': result.get('selected_sheet', ''),
        'total_rows': result.get('total_rows', 0),
        'skipped_rows': result.get('skipped_rows', 0),
        'mapped_columns': result.get('mapped_columns', []),
        'preview_items': result['items'][:50],
    })


@api_bp.route('/compras/import/confirm', methods=['POST'])
@login_required
@csrf.exempt
def compras_import_confirm():
    """Confirm compras import — creates one Specification per row."""
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

    items = payload.get('items', [])
    source_filename = payload.get('source_filename', 'compras_import.xlsx')
    batch_id = str(uuid.uuid4())[:8]

    # Map of compras parser fields → Specification model fields
    # Mirrors exactly the XLSX columns:
    #   A  COLEÇÃO         → collection
    #   D  REFERÊNCIA      → description (material name)
    #   E  COMPOSIÇÃO      → composition
    #   F  CORNER          → corner
    #   G  LINHA           → main_fabric (product line)
    #   H  GRUPO           → main_group
    #   I  SUBGRUPO        → sub_group
    #   J  PREÇO DE VENDA  → target_price
    #   K  FX DE PREÇO     → price_range
    #   M  FORNECEDOR      → supplier
    #   O  COR             → colors
    #   P-U Sizes           → pilot_size (built by parser)
    #   AB DATA DE ENTREGA → delivery_cd_month
    FIELD_MAPPING = {
        'referencia':       'description',
        'composition':      'composition',
        'corner':           'corner',
        'linha':            'main_fabric',
        'main_group':       'main_group',
        'sub_group':        'sub_group',
        'supplier':         'supplier',
        'colors':           'colors',
        'target_price':     'target_price',
        'price_range':      'price_range',
        'pilot_size':       'pilot_size',
        'delivery_date':    'delivery_cd_month',
        'collection':       'collection',
        'cor_etiqueta':     'tags_kit',
        'origem':           'specific_details',
    }

    # Extra fields stored as JSON in spec.extra_fields
    EXTRA_KEYS = (
        'grade', 'total_pcs', 'packs', 'total_souq',
        'custo_real', 'custo_negociado', 'compra_total', 'aprovado',
    )

    created = 0
    errors_list = []

    for i, item in enumerate(items):
        try:
            spec = Specification()
            spec.user_id = user.id
            spec.pdf_filename = f'compras_import_{batch_id}_{i+1}.xlsx'
            spec.batch_id = batch_id
            spec.processing_status = 'completed'
            spec.processing_stage = 7  # STAGE_COMPLETED
            spec.created_at = datetime.utcnow()
            spec.set_status('in_development')
            spec.is_imported = True
            spec.import_category = 'compras'

            # Set mapped fields
            for src_field, spec_field in FIELD_MAPPING.items():
                value = item.get(src_field)
                if value:
                    setattr(spec, spec_field, str(value))

            # Build ref_souq from sub_group + color + supplier
            ref_parts = []
            if item.get('sub_group'):
                ref_parts.append(item['sub_group'])
            if item.get('colors'):
                ref_parts.append(item['colors'])
            spec.ref_souq = ' - '.join(ref_parts) if ref_parts else f'COMPRA-{batch_id}-{i+1}'

            # Store extra fields as JSON
            extra = {}
            for key in EXTRA_KEYS:
                if item.get(key):
                    extra[key] = item[key]
            if extra:
                spec.extra_fields = json.dumps(extra, ensure_ascii=False)

            db.session.add(spec)
            created += 1
        except Exception as e:
            errors_list.append(f'Linha {i+1}: {str(e)}')
            continue

    db.session.commit()

    logger.info(
        'compras_import_confirm: user=%s batch=%s created=%d errors=%d',
        user.username, batch_id, created, len(errors_list)
    )

    return jsonify({
        'success': True,
        'created': created,
        'errors': errors_list,
        'batch_id': batch_id,
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
        # Include Fluxogama integration status
        item_data['fluxogama_status'] = item.fluxogama_status
        item_data['fluxogama_sent_at'] = (
            item.fluxogama_sent_at.isoformat() if item.fluxogama_sent_at else None
        )
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


# ═══════════════════════════════════════════════════════════════════════
# OAZ Integration Endpoints
# ═══════════════════════════════════════════════════════════════════════

@api_bp.route('/oaz/health', methods=['GET'])
@login_required
def oaz_health():
    """GET /api/oaz/health — Test OAZ connectivity and fetch schema."""
    try:
        client = OazClient()
        schema = client.get_schema()
        return jsonify({
            'success': True,
            'schema_keys': len(schema) if isinstance(schema, dict) else 0,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        })
    except OazConfigError as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro de conexão: {str(e)}'}), 502


@api_bp.route('/oaz/mapping', methods=['GET', 'POST'])
@login_required
@csrf.exempt
def oaz_mapping():
    """
    GET  /api/oaz/mapping — List all WSID mappings.
    POST /api/oaz/mapping — Bulk upsert WSID mappings.

    POST body:
        {"mappings": [{"field_key": "uno.10", "text_value": "ACESSÓRIOS", "wsid_value": "9283"}, ...]}
    """
    if request.method == 'GET':
        query = OazValueMap.query
        fk_filter = request.args.get('field_key', '').strip()
        if fk_filter:
            query = query.filter_by(field_key=fk_filter)
        maps = query.order_by(OazValueMap.field_key).all()
        return jsonify({
            'success': True,
            'mappings': [m.to_dict() for m in maps],
            'total': len(maps),
        })

    # POST: bulk upsert
    data = request.get_json(silent=True) or {}
    mappings = data.get('mappings', [])
    if not mappings:
        return jsonify({'success': False, 'error': 'Lista de mappings vazia'}), 400

    created = 0
    updated = 0
    errors = []

    for i, m in enumerate(mappings):
        fk = m.get('field_key', '').strip()
        tv = m.get('text_value', '').strip()
        wv = m.get('wsid_value', '').strip()

        if not fk or not tv or not wv:
            errors.append(f'Mapping #{i}: campos obrigatórios faltando')
            continue

        text_norm = normalize_text(tv)

        existing = OazValueMap.query.filter_by(
            field_key=fk, text_norm=text_norm
        ).first()

        if existing:
            existing.wsid_value = wv
            existing.text_value = tv
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            db.session.add(OazValueMap(
                field_key=fk,
                text_value=tv,
                text_norm=text_norm,
                wsid_value=wv,
            ))
            created += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'created': created,
        'updated': updated,
        'errors': errors,
    })


@api_bp.route('/fichas/<int:ficha_id>/oaz/preview', methods=['GET'])
@login_required
def oaz_preview(ficha_id):
    """GET /api/fichas/<id>/oaz/preview — Preview OAZ payload for all items."""
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    items = FichaTecnicaItem.query.filter_by(ficha_id=ficha.id).all()
    if not items:
        return jsonify({'success': False, 'error': 'Nenhum item nesta ficha'}), 404

    oaz_map = get_oaz_map_lookup(db.session)

    results = []
    total_errors = 0
    total_warnings = 0

    for item in items:
        result = build_oaz_payload(ficha, item, oaz_map)
        validation = validate_oaz_payload(result['payload'])

        total_errors += len(validation['errors'])
        total_warnings += len(validation['warnings'])

        # Clean internal fields from payload for display
        display_payload = {
            k: v for k, v in result['payload'].items() if not k.startswith('_')
        }

        results.append({
            'item_id': item.id,
            'item_ref': item.item_no_ref_supplier,
            'oaz_reference': item.oaz_reference,
            'payload': display_payload,
            'valid': validation['ok'],
            'errors': validation['errors'],
            'warnings': validation['warnings'],
            'fallbacks': result.get('fallbacks', []),
            'current_status': item.oaz_status,
            'payload_hash': compute_payload_hash(result['payload']),
        })

    return jsonify({
        'success': True,
        'ficha_id': ficha.id,
        'total_items': len(results),
        'total_errors': total_errors,
        'total_warnings': total_warnings,
        'ready_to_push': total_errors == 0,
        'items': results,
    })


@api_bp.route('/fichas/<int:ficha_id>/oaz/push', methods=['POST'])
@login_required
@csrf.exempt
def oaz_push(ficha_id):
    """
    POST /api/fichas/<id>/oaz/push — Push items to OAZ.

    Body JSON:
        {
            "dry_run": bool (default false),
            "force": bool (default false — skip idempotency check),
            "item_ids": [int, ...] (optional — push only specific items)
        }
    """
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    data = request.get_json(silent=True) or {}
    dry_run = data.get('dry_run', False)
    force = data.get('force', False)
    item_ids = data.get('item_ids')

    query = FichaTecnicaItem.query.filter_by(ficha_id=ficha.id)
    if item_ids:
        query = query.filter(FichaTecnicaItem.id.in_(item_ids))
    items = query.all()

    if not items:
        return jsonify({'success': False, 'error': 'Nenhum item encontrado'}), 404

    oaz_map = get_oaz_map_lookup(db.session)

    # Initialize client (will raise OazConfigError if not configured)
    try:
        client = OazClient()
    except OazConfigError as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    results = []
    batch_delay = 0.1  # 100ms between pushes

    for i, item in enumerate(items):
        result = build_oaz_payload(ficha, item, oaz_map)
        validation = validate_oaz_payload(result['payload'])
        payload_hash = compute_payload_hash(result['payload'])

        # Clean payload (remove internal metadata)
        clean_payload = {
            k: v for k, v in result['payload'].items() if not k.startswith('_')
        }

        # Validation gate
        if not validation['ok']:
            item.oaz_status = 'ERROR'
            item.oaz_last_error = json.dumps(validation['errors'], ensure_ascii=False)
            db.session.commit()
            results.append({
                'item_id': item.id,
                'status': 'VALIDATION_ERROR',
                'errors': validation['errors'],
            })
            continue

        # Idempotency check
        if (
            not force
            and item.oaz_status == 'SENT'
            and item.oaz_payload_hash == payload_hash
        ):
            results.append({
                'item_id': item.id,
                'status': 'SKIPPED_IDEMPOTENT',
                'message': 'Payload identico ao último envio.',
            })
            continue

        # Dry run
        if dry_run:
            results.append({
                'item_id': item.id,
                'status': 'DRY_RUN',
                'payload': clean_payload,
                'payload_hash': payload_hash,
            })
            continue

        # ── Actual push ────────────────────────────────────────────────
        try:
            response = client.push_modelo(clean_payload)
            item.oaz_status = 'SENT'
            item.oaz_pushed_at = datetime.utcnow()
            item.oaz_payload_hash = payload_hash
            item.oaz_last_error = None
            item.oaz_last_response = json.dumps(response, ensure_ascii=False, default=str)[:2000]
            item.oaz_remote_id = str(response.get('id', response.get('ws_id', '')))
            db.session.commit()

            results.append({
                'item_id': item.id,
                'status': 'SENT',
                'response': response,
            })
        except Exception as e:
            item.oaz_status = 'ERROR'
            item.oaz_last_error = str(e)[:2000]
            db.session.commit()

            results.append({
                'item_id': item.id,
                'status': 'ERROR',
                'error': str(e),
            })

        # Batch delay between items
        if i < len(items) - 1:
            time.sleep(batch_delay)

    sent = sum(1 for r in results if r['status'] == 'SENT')
    skipped = sum(1 for r in results if r['status'] == 'SKIPPED_IDEMPOTENT')
    failed = sum(1 for r in results if r['status'] in ('ERROR', 'VALIDATION_ERROR'))
    dry = sum(1 for r in results if r['status'] == 'DRY_RUN')

    return jsonify({
        'success': True,
        'ficha_id': ficha.id,
        'dry_run': dry_run,
        'summary': {
            'total': len(results),
            'sent': sent,
            'skipped_idempotent': skipped,
            'failed': failed,
            'dry_run': dry,
        },
        'items': results,
    })


@api_bp.route('/fichas/<int:ficha_id>/oaz/status', methods=['GET'])
@login_required
def oaz_status(ficha_id):
    """GET /api/fichas/<id>/oaz/status — Current OAZ status for all items."""
    user = User.query.get(session.get('user_id'))
    if not user:
        return jsonify({'success': False, 'error': 'Sessao invalida'}), 401

    ficha = FichaTecnica.query.get_or_404(ficha_id)
    if not _ensure_user_access(user, ficha):
        return jsonify({'success': False, 'error': 'Acesso negado'}), 403

    items = FichaTecnicaItem.query.filter_by(ficha_id=ficha.id).all()

    statuses = []
    counts = {'PENDING': 0, 'SENT': 0, 'ERROR': 0, 'NONE': 0}

    for item in items:
        status = item.oaz_status or 'NONE'
        counts[status] = counts.get(status, 0) + 1
        statuses.append({
            'item_id': item.id,
            'item_ref': item.item_no_ref_supplier,
            'oaz_status': status,
            'oaz_pushed_at': item.oaz_pushed_at.isoformat() if item.oaz_pushed_at else None,
            'oaz_remote_id': item.oaz_remote_id,
            'oaz_last_error': item.oaz_last_error,
            'oaz_payload_hash': item.oaz_payload_hash,
        })

    return jsonify({
        'success': True,
        'ficha_id': ficha.id,
        'total': len(statuses),
        'counts': counts,
        'items': statuses,
    })
