"""
OAZ Banco de Dados import routes (admin-only).

Provides admin-only XLSX upload with auto-detect field_key + preview/confirm
workflow to populate oaz_value_map with WSIDs from Fluxogama database exports.

Flow:
  1. GET  /admin/bancos               → render import page
  2. POST /api/admin/bancos/preview   → auto-detect field_key per file, parse, return stats + token
  3. POST /api/admin/bancos/confirm   → upsert cached data into DB (per-file field_key)
  4. GET  /api/admin/bancos/status/<id>→ poll background job progress
"""
import threading
import uuid
import unicodedata
import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, session
from app.extensions import csrf, db
from app.utils.auth import admin_required
from app.utils.banco_parser import parse_banco_xlsx
from app.models.oaz_value_map import OazValueMap

oaz_banco_bp = Blueprint('oaz_banco', __name__)

# ── Thread-safe stores ───────────────────────────────────────────────
_lock = threading.Lock()
_PREVIEW_CACHE = {}          # {token: {files, admin_id, created_at}}
_IMPORT_JOBS = {}            # {job_id: {status, files, ...}}
_PREVIEW_TTL = timedelta(minutes=30)
_JOB_TTL = timedelta(hours=1)
_MAX_CONCURRENT_JOBS = 3

# ── Field key options (used for overrides + stats display) ───────────
FIELD_KEY_OPTIONS = [
    ('uno.10', 'Categoria de Produto'),
    ('uno.11', 'Grupo'),
    ('uno.12', 'Sub Grupo'),
    ('uno.15', 'Grade / Tamanho'),
    ('uno.18', 'Linha'),
    ('uno.24', 'Material Principal'),
    ('uno.50', 'NCM'),
]

_VALID_FIELD_KEYS = {k for k, _ in FIELD_KEY_OPTIONS}
_FIELD_KEY_LABELS = {k: lbl for k, lbl in FIELD_KEY_OPTIONS}

# ── Auto-detect mapping ─────────────────────────────────────────────
# Each entry: (alias_string, field_key).
# Sorted by length descending at runtime so longest match wins.
_AUTO_DETECT_ALIASES = [
    # uno.10 - Categoria de Produto
    ('categoria de produto',    'uno.10'),
    ('categoria produto',       'uno.10'),
    ('categoria',               'uno.10'),
    # uno.11 - Grupo
    ('grupo',                   'uno.11'),
    # uno.12 - Sub Grupo
    ('sub grupo',               'uno.12'),
    ('subgrupo',                'uno.12'),
    ('sub-grupo',               'uno.12'),
    # uno.15 - Grade / Tamanho
    ('grade tamanho',           'uno.15'),
    ('grade de tamanho',        'uno.15'),
    ('tamanho',                 'uno.15'),
    ('grade',                   'uno.15'),
    # uno.18 - Linha
    ('linha',                   'uno.18'),
    # uno.24 - Material Principal
    ('materiais principais',    'uno.24'),
    ('mateirais principais',    'uno.24'),  # common typo
    ('material principal',      'uno.24'),
    ('materiais',               'uno.24'),
    ('material',                'uno.24'),
    # uno.50 - NCM
    ('ncm',                     'uno.50'),
]

# Sort by alias length descending so longest match wins (more specific first)
_AUTO_DETECT_ALIASES.sort(key=lambda x: len(x[0]), reverse=True)


# ── Helpers ──────────────────────────────────────────────────────────

def _normalize_text(text):
    """Upper, strip accents, collapse spaces, strip."""
    if not text:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(text))
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    ascii_text = re.sub(r'\s+', ' ', ascii_text).strip().upper()
    return ascii_text


def _normalize_for_detect(text):
    """Lowercase, strip accents, replace _/- with spaces, collapse."""
    if not text:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(text))
    ascii_text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    ascii_text = ascii_text.lower()
    # Replace common separators with space
    ascii_text = re.sub(r'[_\-–—/\\]+', ' ', ascii_text)
    ascii_text = re.sub(r'\s+', ' ', ascii_text).strip()
    # Remove "banco de dados" and "banco" prefix
    ascii_text = re.sub(r'^banco\s*(de\s*dados)?\s*', '', ascii_text).strip()
    # Remove trailing "banco de dados"
    ascii_text = re.sub(r'\s*banco\s*(de\s*dados)?\s*$', '', ascii_text).strip()
    return ascii_text


def detect_field_key(filename, sheet_name=''):
    """
    Auto-detect field_key from filename/sheet name.

    Priority: filename → sheet_name → None.
    Uses contains-matching with longest-match-wins.

    Returns: (field_key, source) or (None, None)
        source = 'filename' | 'sheet_name'
    """
    # Try filename first (strip extension)
    base = filename.rsplit('.', 1)[0] if '.' in filename else filename
    norm_filename = _normalize_for_detect(base)

    for alias, fk in _AUTO_DETECT_ALIASES:
        if alias in norm_filename:
            return fk, 'filename'

    # Try sheet name
    if sheet_name:
        norm_sheet = _normalize_for_detect(sheet_name)
        for alias, fk in _AUTO_DETECT_ALIASES:
            if alias in norm_sheet:
                return fk, 'sheet_name'

    return None, None


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
                    ON CONFLICT (field_key, text_norm)
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


def _process_confirm_job(app, job_id, files_data):
    """Background thread: upsert items from confirmed preview (per-file field_key)."""
    with app.app_context():
        with _lock:
            job = _IMPORT_JOBS.get(job_id)
            if not job:
                return
            job['status'] = 'processing'
            job['started_at'] = datetime.utcnow()

        total_created = 0
        total_updated = 0

        for idx, fd in enumerate(files_data):
            filename = fd['filename']
            field_key = fd['field_key']
            file_items = fd['items']

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
    Parse uploaded XLSX files without saving. Auto-detects field_key per file.
    Accepts optional per-file overrides via form data.

    Form data:
        files[]: one or more XLSX files
        override_<filename>: optional field_key override for a specific file
    """
    files = request.files.getlist('files[]')
    if not files:
        files = request.files.getlist('files')
    if not files:
        return jsonify(success=False, error='Nenhum arquivo enviado.'), 400

    files_result = []
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

        # Check for override first
        override_key = request.form.get(f'override_{f.filename}', '').strip()

        # Auto-detect field_key
        detected_key, detect_source = detect_field_key(
            f.filename, result.get('sheet_name', '')
        )

        # Use override if valid, else detected
        if override_key and override_key in _VALID_FIELD_KEYS:
            final_key = override_key
            detect_source = 'override'
        elif detected_key:
            final_key = detected_key
        else:
            final_key = None

        fi = {
            'filename': f.filename,
            'sheet_name': result.get('sheet_name', ''),
            'total_rows': result.get('total_rows', 0),
            'skipped_inactive': result.get('skipped_inactive', 0),
            'skipped_invalid': result.get('skipped_invalid', 0),
            'valid_items': len(result.get('items', [])),
            'detected_columns': result.get('detected_columns', {}),
            'field_key': final_key,
            'field_key_label': _FIELD_KEY_LABELS.get(final_key, '?') if final_key else None,
            'detect_source': detect_source,
            'error': result.get('error'),
            'items': result.get('items', []) if result['success'] else [],
        }

        if not final_key and result['success']:
            fi['error'] = 'Tipo de banco não identificado. Use o seletor manual.'

        if result['success'] and final_key:
            valid_items = result['items']
            invalid_count = result.get('skipped_invalid', 0)
            total_valid += len(valid_items)
            total_invalid += invalid_count
            total_rows += result.get('total_rows', 0)

            # Collect valid examples (up to 10 total)
            for item in valid_items[:max(0, 10 - len(examples_valid))]:
                examples_valid.append({
                    'descricao': item['descricao'],
                    'wsid': item['wsid'],
                    'text_norm': _normalize_text(item['descricao']),
                    'field_key': final_key,
                    'source': f.filename,
                })

            # Collect invalid examples with reasons (up to 10 total)
            for inv in result.get('invalid_examples', []):
                if len(examples_invalid) < 10:
                    examples_invalid.append({
                        'descricao': inv.get('descricao', ''),
                        'wsid': inv.get('wsid', ''),
                        'reason': inv.get('reason', 'Desconhecido'),
                        'source': f.filename,
                    })
        else:
            total_rows += result.get('total_rows', 0)

        files_result.append(fi)

    if not files_result:
        return jsonify(success=False, error='Nenhum arquivo válido.'), 400

    # Count how many files have valid items + detected field_key
    importable = [fr for fr in files_result if fr['field_key'] and fr['items']]

    # Generate token bound to current admin
    admin_id = session.get('user_id')
    token = str(uuid.uuid4())[:12]
    with _lock:
        _prune_previews()
        _PREVIEW_CACHE[token] = {
            'files': [{
                'filename': fr['filename'],
                'field_key': fr['field_key'],
                'items': fr['items'],
                'sheet_name': fr['sheet_name'],
                'total_rows': fr['total_rows'],
                'valid_items': fr['valid_items'],
            } for fr in importable],
            'admin_id': admin_id,
            'created_at': datetime.utcnow(),
        }

    # Strip items from response (don't send all rows to browser)
    files_response = []
    for fr in files_result:
        resp = {k: v for k, v in fr.items() if k != 'items'}
        resp['valid_items'] = len(fr['items']) if fr['items'] else fr.get('valid_items', 0)
        files_response.append(resp)

    return jsonify(
        success=True,
        token=token,
        total_rows=total_rows,
        total_valid=total_valid,
        total_invalid=total_invalid,
        total_importable=len(importable),
        files=files_response,
        examples_valid=examples_valid[:10],
        examples_invalid=examples_invalid[:10],
    )


@oaz_banco_bp.route('/api/admin/bancos/confirm', methods=['POST'])
@admin_required
@csrf.exempt
def confirm():
    """
    Confirm a previewed import. Starts background upsert job.
    Supports per-file field_key overrides via overrides dict.

    JSON body:
        token: str (from preview response)
        overrides: dict (optional) {filename: field_key}
    """
    data = request.get_json(silent=True) or {}
    token = data.get('token', '').strip()

    if not token:
        return jsonify(success=False, error='Token não informado.'), 400

    admin_id = session.get('user_id')

    with _lock:
        cached = _PREVIEW_CACHE.pop(token, None)

    if not cached:
        return jsonify(success=False,
                       error='Token expirado ou inválido. Refaça o preview.'), 404

    # Validate token belongs to this admin (replay protection)
    if cached.get('admin_id') != admin_id:
        return jsonify(success=False,
                       error='Token pertence a outro administrador.'), 403

    # Apply overrides if provided
    overrides = data.get('overrides', {})
    files_data = cached['files']
    for fd in files_data:
        if fd['filename'] in overrides:
            override_key = overrides[fd['filename']]
            if override_key in _VALID_FIELD_KEYS:
                fd['field_key'] = override_key

    # Filter out files without field_key or items
    files_data = [fd for fd in files_data if fd.get('field_key') and fd.get('items')]

    if not files_data:
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
        'status': 'queued',
        'total_files': len(files_data),
        'current_file_index': 0,
        'current_filename': '',
        'files': [{
            'filename': fd['filename'],
            'field_key': fd['field_key'],
            'field_key_label': _FIELD_KEY_LABELS.get(fd['field_key'], '?'),
            'sheet_name': fd.get('sheet_name', ''),
            'total_rows': fd.get('total_rows', 0),
            'valid_items': len(fd.get('items', [])),
            'created': 0,
            'updated': 0,
            'status': 'queued',
            'error': None,
        } for fd in files_data],
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
        args=(app, job_id, files_data),
        daemon=True,
    )
    t.start()

    return jsonify(success=True, job_id=job_id, total_files=len(files_data))


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
