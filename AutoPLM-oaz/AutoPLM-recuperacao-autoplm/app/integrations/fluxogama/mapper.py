"""
Fluxogama Payload Mapper
========================
Monta o payload JSON a partir de FichaTecnica (header) + FichaTecnicaItem,
usando o mapeamento configurável em field_map.json.
"""
import json
import os
import re
import unicodedata
from datetime import datetime


_field_map_cache = None


def _load_field_map():
    """Load and cache field_map.json."""
    global _field_map_cache
    if _field_map_cache is not None:
        return _field_map_cache
    map_path = os.path.join(os.path.dirname(__file__), 'field_map.json')
    with open(map_path, 'r', encoding='utf-8') as f:
        _field_map_cache = json.load(f)
    return _field_map_cache


def reload_field_map():
    """Force reload of field_map.json (useful after edits)."""
    global _field_map_cache
    _field_map_cache = None
    return _load_field_map()


def _strip_accents(text):
    """Remove accents for case-insensitive matching."""
    if not isinstance(text, str):
        return str(text)
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in normalized if not unicodedata.combining(c))


def _get_raw_row(item):
    """Parse raw_row JSON from item."""
    if not item.raw_row:
        return {}
    try:
        return json.loads(item.raw_row)
    except (TypeError, ValueError):
        return {}


def _normalize_date(value):
    """Try to convert dd/mm/yyyy → yyyy-mm-dd. Returns original if can't parse."""
    if not value or not isinstance(value, str):
        return value
    value = value.strip()
    for fmt_in, fmt_out in [
        (r'^\d{2}/\d{2}/\d{4}$', '%d/%m/%Y'),
        (r'^\d{2}-\d{2}-\d{4}$', '%d-%m-%Y'),
        (r'^\d{4}-\d{2}-\d{2}', '%Y-%m-%d'),  # already ISO
    ]:
        if re.match(fmt_in, value):
            try:
                dt = datetime.strptime(value[:10], fmt_out)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
    return value


def _raw_row_lookup(raw_row, keys):
    """
    Case-insensitive, accent-insensitive lookup in raw_row.
    Tries exact match first, then normalized match.
    """
    # Exact match first
    for key in keys:
        val = raw_row.get(key)
        if val is not None and str(val).strip():
            return val

    # Normalized match (case + accent insensitive)
    normalized_rr = {}
    for k, v in raw_row.items():
        norm_key = _strip_accents(k).lower().strip()
        normalized_rr[norm_key] = v

    for key in keys:
        norm_key = _strip_accents(key).lower().strip()
        val = normalized_rr.get(norm_key)
        if val is not None and str(val).strip():
            return val

    return None


def _resolve_value(field_cfg, item, ficha, raw_row):
    """
    Resolve a single field value following the priority chain:
    1. model_field on item
    2. header_field on ficha
    3. raw_row_keys on item's raw_row (case-insensitive)
    4. default
    Returns (value, source_description)
    """
    # 1. model_field
    model_field = field_cfg.get('model_field')
    if model_field:
        val = getattr(item, model_field, None)
        if val is not None and str(val).strip():
            return val, f'item.{model_field}'

    # 2. header_field
    header_field = field_cfg.get('header_field')
    if header_field:
        val = getattr(ficha, header_field, None)
        if val is not None and str(val).strip():
            return val, f'ficha.{header_field}'

    # 3. raw_row_keys (case-insensitive)
    raw_keys = field_cfg.get('raw_row_keys', [])
    if raw_keys:
        val = _raw_row_lookup(raw_row, raw_keys)
        if val is not None and str(val).strip():
            return val, 'raw_row'

    # 4. default
    default = field_cfg.get('default')
    if default is not None:
        return default, 'default'

    return None, None


def _resolve_template(template_str, item, ficha, raw_row):
    """Resolve a template string like '{oaz_reference}'."""
    def replacer(match):
        field_name = match.group(1)
        # Try item field first
        val = getattr(item, field_name, None)
        if val is not None and str(val).strip():
            return str(val).strip()
        # Try ficha header
        val = getattr(ficha, field_name, None)
        if val is not None and str(val).strip():
            return str(val).strip()
        # Try raw_row (case-insensitive)
        val = _raw_row_lookup(raw_row, [field_name])
        if val is not None and str(val).strip():
            return str(val).strip()
        return ''

    result = re.sub(r'\{(\w+)\}', replacer, template_str)
    result = re.sub(r'\s*-\s*-\s*', ' - ', result)
    result = re.sub(r'^\s*-\s*|\s*-\s*$', '', result)
    return result.strip()


def _compute_ws_id(ficha, item):
    """Generate deterministic ws_id."""
    return f"ficha:{ficha.id}|item:{item.id}"


def _compute_cores(item):
    """Build cores array from item.cor_sistema."""
    cor = getattr(item, 'cor_sistema', None)
    if not cor or not str(cor).strip():
        return []
    return [{"cor": str(cor).strip(), "variante": 0}]


def _normalize_db_value(value, field_cfg):
    """
    Apply db normalization map if configured.
    Returns normalized value or original if no mapping found.
    """
    normalize_map = field_cfg.get('normalize')
    if not normalize_map or not value:
        return value
    str_val = str(value).strip()
    # Try exact match
    if str_val in normalize_map:
        return normalize_map[str_val]
    # Try uppercase match
    upper_val = str_val.upper()
    for k, v in normalize_map.items():
        if k.upper() == upper_val:
            return v
    # No mapping found — return original
    return str_val


def _validate_length(key, value, field_cfg, errors, warnings):
    """
    Validate max_len using truncate_policy:
    - "error": add to errors (do not truncate)
    - "truncate": truncate + add warning
    """
    max_len = field_cfg.get('max_len')
    if not max_len or not value or not isinstance(value, str):
        return value
    if len(value) <= max_len:
        return value

    label = field_cfg.get('label', key)
    policy = field_cfg.get('truncate_policy', 'truncate')

    if policy == 'error':
        errors.append(
            f"Campo '{label}' ({key}) excede {max_len} chars "
            f"({len(value)} chars). Reduza o conteúdo."
        )
        return value  # Keep original for visibility
    else:
        warnings.append(
            f"Campo '{label}' ({key}) truncado de {len(value)} para {max_len} chars."
        )
        return value[:max_len]


def build_payload(ficha, item):
    """
    Build the Fluxogama payload from FichaTecnica (header) + FichaTecnicaItem.

    Returns:
        tuple: (payload_dict, errors_list, warnings_list)
    """
    field_map = _load_field_map()
    raw_row = _get_raw_row(item)
    errors = []
    warnings = []
    payload = {}

    # --- Top-level fields ---
    top_level = field_map.get('top_level', {})
    for key, cfg in top_level.items():
        computed = cfg.get('computed')
        if computed == 'ws_id':
            ws_id_val = _compute_ws_id(ficha, item)
            payload[key] = ws_id_val
            # Also set 'codigo' = ws_id for stable Fluxogama lookup
            payload['codigo'] = ws_id_val
            continue
        if computed == 'cores':
            payload[key] = _compute_cores(item)
            continue

        template = cfg.get('template')
        if template:
            value = _resolve_template(template, item, ficha, raw_row)
            value = _validate_length(key, value, cfg, errors, warnings)
            if cfg.get('required') and not value:
                errors.append(f"Campo obrigatório '{cfg.get('label', key)}' ({key}) está vazio.")
            payload[key] = value or ''
            continue

        value, _source = _resolve_value(cfg, item, ficha, raw_row)
        if value is not None:
            value = str(value).strip()
        value = _validate_length(key, value, cfg, errors, warnings)
        if cfg.get('required') and not value:
            errors.append(f"Campo obrigatório '{cfg.get('label', key)}' ({key}) está vazio.")
        payload[key] = value or ''

    # --- uno.X fields ---
    uno_fields = field_map.get('uno_fields', {})
    for key, cfg in uno_fields.items():
        computed = cfg.get('computed')
        if computed == 'integration_status':
            payload[key] = ''
            continue

        field_type = cfg.get('type', 'text')
        value, _source = _resolve_value(cfg, item, ficha, raw_row)

        if value is not None:
            if field_type == 'date':
                value = _normalize_date(str(value))
            elif field_type == 'numeric':
                if isinstance(value, (int, float)):
                    value = value
                else:
                    try:
                        value = float(str(value).replace(',', '.'))
                    except (ValueError, TypeError):
                        value = str(value).strip()
            elif field_type == 'db':
                value = str(value).strip()
                value = _normalize_db_value(value, cfg)
            else:
                value = str(value).strip()

        # Validate max_len for string values
        if isinstance(value, str):
            value = _validate_length(key, value, cfg, errors, warnings)

        # Validate required
        if cfg.get('required') and (value is None or value == ''):
            label = cfg.get('label', key)
            errors.append(f"Campo obrigatório '{label}' ({key}) está vazio.")

        # Warn on empty db fields
        if field_type == 'db' and value is not None and isinstance(value, str) and not value:
            label = cfg.get('label', key)
            warnings.append(f"Campo BD '{label}' ({key}) está vazio — pode causar erro no Fluxogama.")

        payload[key] = value if value is not None else ''

    return payload, errors, warnings


def validate_payload(payload, existing_errors=None):
    """
    Extra validation pass on a built payload.
    Checks all required fields defined in field_map.json.
    Skips fields already reported in existing_errors to avoid duplicates.
    """
    existing_errors = existing_errors or []
    # Extract field keys already mentioned in existing errors (e.g. "(colecao)")
    already_flagged = set()
    for err in existing_errors:
        # Match pattern like "(colecao)" or "(uno.1)"
        import re
        match = re.search(r'\(([^)]+)\)', err)
        if match:
            already_flagged.add(match.group(1))

    errors = []
    field_map = _load_field_map()

    def _is_empty(val):
        """True if None or blank string. Does NOT flag 0 or False."""
        return val is None or (isinstance(val, str) and val.strip() == "")

    # Check top_level required fields
    for key, cfg in field_map.get('top_level', {}).items():
        if key in already_flagged:
            continue
        if cfg.get('required') and _is_empty(payload.get(key)):
            label = cfg.get('label', key)
            errors.append(f"Campo obrigatório '{label}' ({key}) está vazio.")

    # Check uno_fields required fields
    for key, cfg in field_map.get('uno_fields', {}).items():
        if key in already_flagged:
            continue
        if cfg.get('required') and _is_empty(payload.get(key)):
            label = cfg.get('label', key)
            errors.append(f"Campo obrigatório '{label}' ({key}) está vazio.")

    return errors

