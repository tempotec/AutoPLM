"""
OAZ Banco de Dados import routes (admin-only).

Provides admin-only XLSX upload with preview/confirm workflow
to populate oaz_value_map with WSIDs from Fluxogama database exports.

Flow:
  1. GET  /admin/bancos               → render import page
  2. POST /api/admin/bancos/preview    → parse without saving, return stats + token
  3. POST /api/admin/bancos/confirm    → upsert cached data into DB
  4. GET  /api/admin/bancos/status/<id>→ poll background job progress
"""
import threading
import uuid
import unicodedata
import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from app.extensions import csrf, db
from app.utils.auth import admin_required
from app.utils.banco_parser import parse_banco_xlsx
from app.models.oaz_value_map import OazValueMap

oaz_banco_bp = Blueprint('oaz_banco', __name__)

# ── Thread-safe stores ───────────────────────────────────────────────
_lock = threading.Lock()
_PREVIEW_CACHE = {}          # {token: {field_key, items, files_info, created_at}}
_IMPORT_JOBS = {}            # {job_id: {status, files, ...}}
_PREVIEW_TTL = timedelta(minutes=30)
_JOB_TTL = timedelta(hours=1)
_MAX_CONCURRENT_JOBS = 3

# ── Field key options ────────────────────────────────────────────────
FIELD_KEY_OPTIONS = [
    ('uno.10', 'Categoria de Produto'),
    ('uno.11', 'Grupo'),
    ('uno.12', 'Sub Grupo'),
    ('uno.15', 'Grade / Tamanho'),
    ('uno.18', 'Linha'),
    ('uno.24', 'Material Principal'),
    ('uno.50', 'NCM'),
]

# ── Helpers ──────────────────────────────────────────────────────────

def _normalize_text(text):
    """Upper, strip accents, collapse spaces, strip."""
    if not text:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(text))
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    ascii_text = re.sub(r'\s+', ' ', ascii_text).strip().upper()
    return ascii_text


def _prune_previews():
    """Remove expired preview tokens. Must be called under lock."""
    now = datetime.utcnow()
    expired = [t for t, p in _PREVIEW_CACHE.items()
               if (now - p['created_at']) > _PREVIEW_TTL]
    for t in expired:
        del _PREVIEW_CACHE[t]


def _prune_old_jobs():
    """Remove jobs older than TTL. Must be called under lock."""
    now = datetime.utcnow()
    expired = [jid for jid, j in _IMPORT_JOBS.items()
               if j.get('ended_at') and (now - j['ended_at']) > _JOB_TTL]
    for jid in expired:
        del _IMPORT_JOBS[jid]


def _batch_upsert(field_key, items, source_name=None, batch_size=500):
    """
    Batch upsert items into oaz_value_map.
    Returns (created, updated, errors).
    """
    from sqlalchemy import text as sa_text

    created = 0
    updated = 0
    errors = []

    # Preload existing text_norm values
    existing = set()
    try:
        rows = db.session.execute(
            sa_text("SELECT text_norm FROM oaz_value_map WHERE field_key = :fk"),
            {'fk': field_key}
        ).fetchall()
        existing = {r[0] for r in rows}
    except Exception:
        pass

    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        try:
            for item in batch:
                text_value = item['descricao']
                text_norm = _normalize_text(text_value)
                wsid_value = item['wsid']

                if not text_norm or not wsid_value:
                    continue

                is_new = text_norm not in existing

                stmt = sa_text("""
                    INSERT INTO oaz_value_map
                        (field_key, text_value, text_norm, wsid_value, source_name, created_at, updated_at)
                    VALUES
                        (:field_key, :text_value, :text_norm, :wsid_value, :source_name, NOW(), NOW())
                    ON CONFLICT ON CONSTRAINT uq_oaz_map_field_text
                    DO UPDATE SET
                        text_value = EXCLUDED.text_value,
                        wsid_value = EXCLUDED.wsid_value,
                        source_name = EXCLUDED.source_name,
                        updated_at = NOW()
                """)
                db.session.execute(stmt, {
                    'field_key': field_key,
                    'text_value': text_value,
                    'text_norm': text_norm,
                    'wsid_value': wsid_value,
                    'source_name': source_name,
                })

                if is_new:
                    created += 1
                    existing.add(text_norm)
                else:
                    updated += 1

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            errors.append(f'Batch {i // batch_size + 1}: {str(e)[:200]}')

    return created, updated, errors


def _process_confirm_job(app, job_id, field_key, all_items, files_info):
    """Background thread: upsert all items from a confirmed preview."""
    with app.app_context():
        with _lock:
            job = _IMPORT_JOBS.get(job_id)
            if not job:
                return
            job['status'] = 'processing'
            job['started_at'] = datetime.utcnow()

        total_created = 0
        total_updated = 0

        # Group items by source file for per-file tracking
        for idx, fi in enumerate(files_info):
            filename = fi['filename']
            start = fi.get('items_start', 0)
            end = fi.get('items_end', 0)
            file_items = all_items[start:end]

            with _lock:
                job['current_file_index'] = idx
                job['current_filename'] = filename

            if not file_items:
                with _lock:
                    job['files'][idx]['status'] = 'empty'
                    job['files'][idx]['error'] = 'Nenhum item válido.'
                continue

            created, updated, errors = _batch_upsert(
                field_key, file_items, source_name=filename
            )
            total_created += created
            total_updated += updated

            with _lock:
                job['files'][idx]['created'] = created
                job['files'][idx]['updated'] = updated
                job['files'][idx]['status'] = 'done' if not errors else 'partial'
                if errors:
                    job['files'][idx]['error'] = '; '.join(errors)

        with _lock:
            job['status'] = 'done'
            job['ended_at'] = datetime.utcnow()
            job['total_created'] = total_created
            job['total_updated'] = total_updated


# ── Routes ───────────────────────────────────────────────────────────

@oaz_banco_bp.route('/admin/bancos')
@admin_required
def import_view():
    """Render the Banco de Dados import page (admin-only)."""
    from sqlalchemy import func
    counts = db.session.query(
        OazValueMap.field_key, func.count(OazValueMap.id)
    ).group_by(OazValueMap.field_key).all()
    counts_map = {k: v for k, v in counts}

    return render_template('oaz_banco_import.html',
                           field_options=FIELD_KEY_OPTIONS,
                           mapping_counts=counts_map)


@oaz_banco_bp.route('/api/admin/bancos/preview', methods=['POST'])
@admin_required
@csrf.exempt
def preview():
    """
    Parse uploaded XLSX files without saving. Returns stats + preview token.

    Form data:
        field_key: str (e.g. "uno.12")
        files[]: one or more XLSX files
    """
    field_key = request.form.get('field_key', '').strip()
    valid_keys = {k for k, _ in FIELD_KEY_OPTIONS}

    if field_key not in valid_keys:
        return jsonify(success=False, error=f'field_key inválido: {field_key}'), 400

    files = request.files.getlist('files[]')
    if not files:
        files = request.files.getlist('files')
    if not files:
        return jsonify(success=False, error='Nenhum arquivo enviado.'), 400

    all_items = []
    files_info = []
    total_valid = 0
    total_invalid = 0
    total_rows = 0
    examples_valid = []
    examples_invalid = []

    for f in files:
        if not f.filename:
            continue
        if not f.filename.lower().endswith('.xlsx'):
            return jsonify(success=False,
                           error=f'Arquivo "{f.filename}" não é .xlsx'), 400
        file_bytes = f.read()
        if len(file_bytes) > 50 * 1024 * 1024:
            return jsonify(success=False,
                           error=f'Arquivo "{f.filename}" excede 50MB.'), 400

        result = parse_banco_xlsx(file_bytes)

        fi = {
            'filename': f.filename,
            'sheet_name': result.get('sheet_name', ''),
            'total_rows': result.get('total_rows', 0),
            'skipped_inactive': result.get('skipped_inactive', 0),
            'skipped_invalid': result.get('skipped_invalid', 0),
            'valid_items': len(result.get('items', [])),
            'error': result.get('error'),
            'items_start': len(all_items),  # index into all_items
        }

        if result['success']:
            valid_items = result['items']
            invalid_count = result.get('skipped_invalid', 0)

            all_items.extend(valid_items)
            total_valid += len(valid_items)
            total_invalid += invalid_count
            total_rows += result.get('total_rows', 0)

            # Collect examples (up to 10 total)
            for item in valid_items[:max(0, 10 - len(examples_valid))]:
                examples_valid.append({
                    'descricao': item['descricao'],
                    'wsid': item['wsid'],
                    'text_norm': _normalize_text(item['descricao']),
                    'source': f.filename,
                })
        else:
            total_rows += result.get('total_rows', 0)

        fi['items_end'] = len(all_items)
        files_info.append(fi)

    if not files_info:
        return jsonify(success=False, error='Nenhum arquivo válido.'), 400

    # Generate token and cache parsed data
    token = str(uuid.uuid4())[:12]
    with _lock:
        _prune_previews()
        _PREVIEW_CACHE[token] = {
            'field_key': field_key,
            'items': all_items,
            'files_info': files_info,
            'created_at': datetime.utcnow(),
        }

    return jsonify(
        success=True,
        token=token,
        field_key=field_key,
        total_rows=total_rows,
        total_valid=total_valid,
        total_invalid=total_invalid,
        files=files_info,
        examples_valid=examples_valid[:10],
    )


@oaz_banco_bp.route('/api/admin/bancos/confirm', methods=['POST'])
@admin_required
@csrf.exempt
def confirm():
    """
    Confirm a previewed import. Starts background upsert job.

    JSON body:
        token: str (from preview response)
    """
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()

    if not token:
        return jsonify(success=False, error='Token não informado.'), 400

    with _lock:
        cached = _PREVIEW_CACHE.pop(token, None)

    if not cached:
        return jsonify(success=False,
                       error='Token expirado ou inválido. Refaça o preview.'), 404

    field_key = cached['field_key']
    all_items = cached['items']
    files_info = cached['files_info']

    if not all_items:
        return jsonify(success=False, error='Nenhum item válido para importar.'), 400

    # Check concurrent job limit
    with _lock:
        _prune_old_jobs()
        active = sum(1 for j in _IMPORT_JOBS.values() if j['status'] == 'processing')
        if active >= _MAX_CONCURRENT_JOBS:
            return jsonify(success=False,
                           error=f'Limite de {_MAX_CONCURRENT_JOBS} jobs atingido.'), 429

    # Create job
    job_id = str(uuid.uuid4())[:8]
    job = {
        'job_id': job_id,
        'field_key': field_key,
        'status': 'queued',
        'total_files': len(files_info),
        'current_file_index': 0,
        'current_filename': '',
        'files': [{
            'filename': fi['filename'],
            'sheet_name': fi.get('sheet_name', ''),
            'total_rows': fi.get('total_rows', 0),
            'valid_items': fi.get('valid_items', 0),
            'created': 0,
            'updated': 0,
            'status': 'queued',
            'error': None,
        } for fi in files_info],
        'total_created': 0,
        'total_updated': 0,
        'created_at': datetime.utcnow(),
        'started_at': None,
        'ended_at': None,
    }

    with _lock:
        _IMPORT_JOBS[job_id] = job

    # Start background thread
    from flask import current_app
    app = current_app._get_current_object()
    t = threading.Thread(
        target=_process_confirm_job,
        args=(app, job_id, field_key, all_items, files_info),
        daemon=True,
    )
    t.start()

    return jsonify(success=True, job_id=job_id, total_files=len(files_info))


@oaz_banco_bp.route('/api/admin/bancos/status/<job_id>')
@admin_required
def import_status(job_id):
    """Poll the status of a confirm/import job."""
    with _lock:
        job = _IMPORT_JOBS.get(job_id)

    if not job:
        return jsonify(success=False, error='Job não encontrado.'), 404

    def _dt(d):
        return d.isoformat() + 'Z' if d else None

    return jsonify(
        success=True,
        job_id=job['job_id'],
        field_key=job['field_key'],
        status=job['status'],
        total_files=job['total_files'],
        current_file_index=job.get('current_file_index', 0),
        current_filename=job.get('current_filename', ''),
        files=job['files'],
        total_created=job.get('total_created', 0),
        total_updated=job.get('total_updated', 0),
        created_at=_dt(job.get('created_at')),
        started_at=_dt(job.get('started_at')),
        ended_at=_dt(job.get('ended_at')),
    )
