"""
OAZ Banco de Dados import routes.

Provides batch XLSX upload with background thread processing
to populate oaz_value_map with WSIDs from Fluxogama database exports.
"""
import threading
import uuid
import unicodedata
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from app.extensions import csrf, db
from app.utils.auth import login_required
from app.utils.banco_parser import parse_banco_xlsx
from app.models.oaz_value_map import OazValueMap

oaz_banco_bp = Blueprint('oaz_banco', __name__)

# ── Thread-safe job store ────────────────────────────────────────────
_jobs_lock = threading.Lock()
_IMPORT_JOBS = {}           # {job_id: {status, files, ...}}
_JOB_TTL = timedelta(hours=1)
_MAX_CONCURRENT_JOBS = 3

# ── Field key options ────────────────────────────────────────────────
FIELD_KEY_OPTIONS = [
    ('uno.10', 'Categoria de Produto'),
    ('uno.11', 'Grupo'),
    ('uno.12', 'Sub Grupo'),
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
    import re
    ascii_text = re.sub(r'\s+', ' ', ascii_text).strip().upper()
    return ascii_text


def _prune_old_jobs():
    """Remove jobs older than TTL. Must be called under lock."""
    now = datetime.utcnow()
    expired = [jid for jid, j in _IMPORT_JOBS.items()
               if j.get('ended_at') and (now - j['ended_at']) > _JOB_TTL]
    for jid in expired:
        del _IMPORT_JOBS[jid]


def _batch_upsert(field_key, items, batch_size=500):
    """
    Batch upsert items into oaz_value_map.
    Preloads existing keys to track created vs updated.

    Returns (created, updated, errors).
    """
    from sqlalchemy import text

    created = 0
    updated = 0
    errors = []

    # Preload existing text_norm values for this field_key
    existing = set()
    try:
        rows = db.session.execute(
            text("SELECT text_norm FROM oaz_value_map WHERE field_key = :fk"),
            {'fk': field_key}
        ).fetchall()
        existing = {r[0] for r in rows}
    except Exception:
        pass  # If query fails, treat all as new

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

                stmt = text("""
                    INSERT INTO oaz_value_map (field_key, text_value, text_norm, wsid_value, created_at, updated_at)
                    VALUES (:field_key, :text_value, :text_norm, :wsid_value, NOW(), NOW())
                    ON CONFLICT ON CONSTRAINT uq_oaz_map_field_text
                    DO UPDATE SET
                        text_value = EXCLUDED.text_value,
                        wsid_value = EXCLUDED.wsid_value,
                        updated_at = NOW()
                """)
                db.session.execute(stmt, {
                    'field_key': field_key,
                    'text_value': text_value,
                    'text_norm': text_norm,
                    'wsid_value': wsid_value,
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


def _process_job(app, job_id, files_data, field_key):
    """Background thread function to process all uploaded files."""
    with app.app_context():
        with _jobs_lock:
            job = _IMPORT_JOBS.get(job_id)
            if not job:
                return
            job['status'] = 'processing'
            job['started_at'] = datetime.utcnow()

        total_created = 0
        total_updated = 0

        for idx, file_info in enumerate(files_data):
            filename = file_info['filename']
            file_bytes = file_info['bytes']

            # Update current file
            with _jobs_lock:
                job['current_file_index'] = idx
                job['current_filename'] = filename

            # Parse
            result = parse_banco_xlsx(file_bytes)

            file_result = {
                'filename': filename,
                'sheet_name': result.get('sheet_name', ''),
                'total_rows': result.get('total_rows', 0),
                'skipped_inactive': result.get('skipped_inactive', 0),
                'skipped_invalid': result.get('skipped_invalid', 0),
                'valid_items': len(result.get('items', [])),
                'created': 0,
                'updated': 0,
                'status': 'error' if not result['success'] else 'pending',
                'error': result.get('error'),
            }

            if result['success'] and result['items']:
                # Batch upsert
                created, updated, errors = _batch_upsert(field_key, result['items'])
                file_result['created'] = created
                file_result['updated'] = updated
                file_result['status'] = 'done' if not errors else 'partial'
                if errors:
                    file_result['error'] = '; '.join(errors)
                total_created += created
                total_updated += updated
            elif result['success'] and not result['items']:
                file_result['status'] = 'empty'
                file_result['error'] = 'Nenhum item válido encontrado.'

            with _jobs_lock:
                job['files'][idx] = file_result

        # Finalize
        with _jobs_lock:
            job['status'] = 'done'
            job['ended_at'] = datetime.utcnow()
            job['total_created'] = total_created
            job['total_updated'] = total_updated


# ── Routes ───────────────────────────────────────────────────────────

@oaz_banco_bp.route('/oaz/banco')
@login_required
def import_view():
    """Render the Banco de Dados import page."""
    # Count existing mappings per field_key
    from sqlalchemy import func
    counts = db.session.query(
        OazValueMap.field_key, func.count(OazValueMap.id)
    ).group_by(OazValueMap.field_key).all()
    counts_map = {k: v for k, v in counts}

    return render_template('oaz_banco_import.html',
                           field_options=FIELD_KEY_OPTIONS,
                           mapping_counts=counts_map)


@oaz_banco_bp.route('/api/oaz/banco/import', methods=['POST'])
@login_required
@csrf.exempt
def import_batch():
    """
    Start a batch import job.

    Form data:
        field_key: str (e.g. "uno.18")
        files[]: multiple XLSX files
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

    # Validate files
    files_data = []
    for f in files:
        if not f.filename:
            continue
        if not f.filename.lower().endswith('.xlsx'):
            return jsonify(success=False,
                           error=f'Arquivo "{f.filename}" não é .xlsx'), 400
        file_bytes = f.read()
        if len(file_bytes) > 50 * 1024 * 1024:  # 50MB limit
            return jsonify(success=False,
                           error=f'Arquivo "{f.filename}" excede 50MB.'), 400
        files_data.append({
            'filename': f.filename,
            'bytes': file_bytes,
        })

    if not files_data:
        return jsonify(success=False, error='Nenhum arquivo válido.'), 400

    # Check concurrent job limit
    with _jobs_lock:
        _prune_old_jobs()
        active = sum(1 for j in _IMPORT_JOBS.values() if j['status'] == 'processing')
        if active >= _MAX_CONCURRENT_JOBS:
            return jsonify(success=False,
                           error=f'Limite de {_MAX_CONCURRENT_JOBS} jobs simultâneos atingido.'), 429

    # Create job
    job_id = str(uuid.uuid4())[:8]
    job = {
        'job_id': job_id,
        'field_key': field_key,
        'status': 'queued',
        'total_files': len(files_data),
        'current_file_index': 0,
        'current_filename': '',
        'files': [{'filename': fd['filename'], 'status': 'queued'} for fd in files_data],
        'total_created': 0,
        'total_updated': 0,
        'created_at': datetime.utcnow(),
        'started_at': None,
        'ended_at': None,
    }

    with _jobs_lock:
        _IMPORT_JOBS[job_id] = job

    # Start background thread
    from flask import current_app
    app = current_app._get_current_object()
    t = threading.Thread(
        target=_process_job,
        args=(app, job_id, files_data, field_key),
        daemon=True,
    )
    t.start()

    return jsonify(success=True, job_id=job_id, total_files=len(files_data))


@oaz_banco_bp.route('/api/oaz/banco/import/status/<job_id>')
@login_required
def import_status(job_id):
    """Poll the status of an import job."""
    with _jobs_lock:
        job = _IMPORT_JOBS.get(job_id)

    if not job:
        return jsonify(success=False, error='Job não encontrado.'), 404

    # Serialize datetimes
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
