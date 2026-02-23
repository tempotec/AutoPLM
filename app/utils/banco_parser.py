"""
Parser for Fluxogama 'Banco de Dados' XLSX files.

These files contain WSID mappings for materials, lines, groups, etc.
Typical columns: Código | WSID | Descrição | Status | ...
"""
import io
import re
import unicodedata
import pandas as pd


# Column name variations we accept (normalized → canonical)
_CODIGO_NAMES = {'codigo', 'cod', 'code', 'id'}
_WSID_NAMES = {'wsid', 'ws_id', 'ws'}
_DESCRICAO_NAMES = {'descricao', 'desc', 'description', 'nome', 'name', 'label'}
_STATUS_NAMES = {'status', 'situacao', 'situação', 'ativo'}


def _normalize_col(name):
    """Normalize column name: strip accents, lowercase, replace non-alnum."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ''
    text = str(name).strip()
    # Remove accents
    nfkd = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in nfkd if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
    return text


def _find_col(columns_norm, candidates):
    """Find first column index matching any candidate name."""
    for idx, name in enumerate(columns_norm):
        if name in candidates:
            return idx
    return None


def _safe_str(value):
    """Convert value to string, preserving leading zeros. Returns None for empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text = str(value).strip()
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text if text else None


def parse_banco_xlsx(file_bytes):
    """
    Parse a Banco de Dados XLSX file.

    Returns dict with:
        success: bool
        items: list of {codigo, wsid, descricao}
        total_rows: int
        skipped_inactive: int
        skipped_invalid: int
        error: str or None
        sheet_name: str
    """
    try:
        stream = io.BytesIO(file_bytes)
        xl = pd.ExcelFile(stream, engine='openpyxl')
        sheet = xl.sheet_names[0]
        df = xl.parse(sheet_name=sheet, header=None)
    except Exception as e:
        return {
            'success': False,
            'items': [],
            'total_rows': 0,
            'skipped_inactive': 0,
            'skipped_invalid': 0,
            'error': f'Erro ao ler XLSX: {str(e)}',
            'sheet_name': '',
        }

    if len(df) < 2:
        return {
            'success': False,
            'items': [],
            'total_rows': 0,
            'skipped_inactive': 0,
            'skipped_invalid': 0,
            'error': 'Arquivo vazio ou sem dados.',
            'sheet_name': sheet,
        }

    # --- Find header row (first row with Código/WSID match) ---
    header_row = None
    for i in range(min(10, len(df))):
        row_vals = df.iloc[i].tolist()
        norms = [_normalize_col(v) for v in row_vals]
        has_codigo = any(n in _CODIGO_NAMES for n in norms)
        has_wsid = any(n in _WSID_NAMES for n in norms)
        if has_codigo or has_wsid:
            header_row = i
            break

    if header_row is None:
        return {
            'success': False,
            'items': [],
            'total_rows': len(df),
            'skipped_inactive': 0,
            'skipped_invalid': 0,
            'error': 'Coluna "Código" ou "WSID" não encontrada.',
            'sheet_name': sheet,
        }

    # --- Map columns ---
    header_vals = df.iloc[header_row].tolist()
    cols_norm = [_normalize_col(v) for v in header_vals]

    codigo_idx = _find_col(cols_norm, _CODIGO_NAMES)
    wsid_idx = _find_col(cols_norm, _WSID_NAMES)
    descricao_idx = _find_col(cols_norm, _DESCRICAO_NAMES)
    status_idx = _find_col(cols_norm, _STATUS_NAMES)

    if codigo_idx is None and wsid_idx is None:
        return {
            'success': False,
            'items': [],
            'total_rows': len(df),
            'skipped_inactive': 0,
            'skipped_invalid': 0,
            'invalid_examples': [],
            'detected_columns': {},
            'error': 'Nenhuma coluna "Código" ou "WSID" encontrada.',
            'sheet_name': sheet,
        }

    # Build detected columns info
    detected_columns = {}
    if wsid_idx is not None:
        detected_columns['wsid'] = str(header_vals[wsid_idx])
    if codigo_idx is not None:
        detected_columns['codigo'] = str(header_vals[codigo_idx])
    if descricao_idx is not None:
        detected_columns['descricao'] = str(header_vals[descricao_idx])
    if status_idx is not None:
        detected_columns['status'] = str(header_vals[status_idx])

    # --- Parse data rows ---
    data = df.iloc[header_row + 1:]
    items = []
    skipped_inactive = 0
    skipped_invalid = 0
    invalid_examples = []  # up to 10, with reason
    _MAX_INVALID_EXAMPLES = 10

    for _, row in data.iterrows():
        vals = row.tolist()

        # Skip inactive rows (if status column exists)
        if status_idx is not None:
            status = _safe_str(vals[status_idx]) if status_idx < len(vals) else None
            if status and status.lower() not in ('ativo', 'active', 'a', '1', 'sim', 'yes'):
                skipped_inactive += 1
                continue

        # Get codigo and wsid
        codigo = _safe_str(vals[codigo_idx]) if codigo_idx is not None and codigo_idx < len(vals) else None
        wsid = _safe_str(vals[wsid_idx]) if wsid_idx is not None and wsid_idx < len(vals) else None
        descricao = _safe_str(vals[descricao_idx]) if descricao_idx is not None and descricao_idx < len(vals) else None

        # Determine final wsid_value: prefer WSID column, fallback to Código
        wsid_value = wsid or codigo
        if not wsid_value:
            skipped_invalid += 1
            if len(invalid_examples) < _MAX_INVALID_EXAMPLES:
                invalid_examples.append({
                    'descricao': descricao or '',
                    'wsid': '',
                    'reason': 'WSID ausente',
                })
            continue

        # Determine text_value: use Descrição if available
        text_value = descricao or ''

        if not text_value:
            skipped_invalid += 1
            if len(invalid_examples) < _MAX_INVALID_EXAMPLES:
                invalid_examples.append({
                    'descricao': '',
                    'wsid': wsid_value,
                    'reason': 'Descrição vazia',
                })
            continue

        items.append({
            'codigo': codigo or '',
            'wsid': wsid_value,
            'descricao': text_value,
        })

    return {
        'success': True,
        'items': items,
        'total_rows': len(data),
        'skipped_inactive': skipped_inactive,
        'skipped_invalid': skipped_invalid,
        'invalid_examples': invalid_examples,
        'detected_columns': detected_columns,
        'error': None,
        'sheet_name': sheet,
    }

