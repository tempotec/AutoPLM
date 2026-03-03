"""
Parser for 'Coleção Picking / Fornecedores' XLSX files (purchased products).
Reads product rows and maps them to Specification-compatible dicts.
"""
import io
import logging
import pandas as pd

logger = logging.getLogger('compras_parser')


# ══════════════════════════════════════════════════════════════════════
# Column mapping: XLSX header (lowercased/stripped) → internal field name
#
# Excel TESTE PLM sheet columns (row 2 = header):
#   A  COLEÇÃO         → collection
#   B  FOTO            → (skip, formula)
#   C  ORIGEM          → origem (extra)
#   D  REFERÊNCIA      → referencia (material name e.g. "Poliéster")
#   E  COMPOSIÇÃO      → composition
#   F  CORNER          → corner
#   G  LINHA           → linha (product line e.g. "ALFAIATARIA")
#   H  GRUPO           → main_group
#   I  SUBGRUPO        → sub_group
#   J  PREÇO DE VENDA  → target_price
#   K  FX DE PREÇO     → price_range
#   L  GRADE           → grade (extra)
#   M  FORNECEDOR      → supplier
#   N  COR ETIQUETA    → cor_etiqueta (extra)
#   O  COR             → colors
#   P  34              → size_34
#   Q  PP/36           → size_pp_36
#   R  P/38            → size_p_38
#   S  M/40            → size_m_40
#   T  G/42            → size_g_42
#   U  GG/44           → size_gg_44
#   V  TT              → total_pcs (extra)
#   W  PACKS           → packs (extra)
#   X  TT SOUQ         → total_souq (extra)
#   Y  CUSTO REAL      → custo_real (extra)
#   Z  CUSTO NEGOCIADO → custo_negociado (extra)
#   AA COMPRA TOTAL    → compra_total (extra)
#   AB DATA DE ENTREGA → delivery_date
# ══════════════════════════════════════════════════════════════════════

_COL_MAP = {
    # A - Coleção
    'coleção':          'collection',
    'colecao':          'collection',
    'coleçao':          'collection',
    # B - Foto (skip)
    'foto':             'foto',
    # C - Origem
    'origem':           'origem',
    # D - Referência (material name)
    'referência':       'referencia',
    'referencia':       'referencia',
    'artigo':           'referencia',
    # E - Composição
    'composição':       'composition',
    'composicao':       'composition',
    'composição ':      'composition',
    # F - Corner
    'corner':           'corner',
    # G - Linha
    'linha':            'linha',
    # H - Grupo
    'grupo':            'main_group',
    # I - Subgrupo
    'subgrupo':         'sub_group',
    # J - Preço de Venda
    'preço de venda':   'target_price',
    'preco de venda':   'target_price',
    # K - Faixa de Preço
    'fx de preço':      'price_range',
    'fx de preco':      'price_range',
    # L - Grade
    'grade':            'grade',
    # M - Fornecedor
    'fornecedor':       'supplier',
    # N - Cor Etiqueta
    'cor etiqueta':     'cor_etiqueta',
    # O - Cor
    'cor':              'colors',
    # P-U - Sizes
    '34':               'size_34',
    'pp/36':            'size_pp_36',
    'p/38':             'size_p_38',
    'm/40':             'size_m_40',
    'g/42':             'size_g_42',
    'gg/44':            'size_gg_44',
    # V-W - Totals
    'tt':               'total_pcs',
    'packs':            'packs',
    # X - TT Souq
    'tt souq':          'total_souq',
    # Y-AA - Costs
    'custo real':       'custo_real',
    'custo negociado':  'custo_negociado',
    'compra total':     'compra_total',
    # AB - Data de Entrega
    'data de entrega':  'delivery_date',
    'aprovado':         'aprovado',
}

# Size columns for building pilot_size string
_SIZE_COLS = [
    ('size_34', '34'),
    ('size_pp_36', 'PP/36'),
    ('size_p_38', 'P/38'),
    ('size_m_40', 'M/40'),
    ('size_g_42', 'G/42'),
    ('size_gg_44', 'GG/44'),
]

# Fields that go directly to Specification model columns
_SPEC_FIELDS = {
    'collection', 'referencia', 'composition', 'corner', 'linha',
    'main_group', 'sub_group', 'target_price', 'price_range',
    'supplier', 'colors', 'delivery_date',
}

# Fields stored in extra_fields JSON
_EXTRA_FIELDS = {
    'origem', 'grade', 'cor_etiqueta', 'total_pcs', 'packs',
    'total_souq', 'custo_real', 'custo_negociado', 'compra_total',
    'aprovado',
}

# Fields to skip completely
_SKIP_FIELDS = {'foto'}


def _normalize_header(val):
    """Lowercase, strip whitespace for matching."""
    if not isinstance(val, str):
        return str(val).strip().lower()
    return val.strip().lower()


def parse_compras_xlsx(file_bytes, sheet_name=None):
    """
    Parse a 'Compras' XLSX file.

    Args:
        file_bytes: bytes of the XLSX file
        sheet_name: name of the sheet to parse (default: first suitable sheet)

    Returns:
        dict with keys: items, sheet_names, selected_sheet, total_rows, errors
    """
    stream = io.BytesIO(file_bytes)

    try:
        xl = pd.ExcelFile(stream, engine='openpyxl')
    except Exception as e:
        return {
            'items': [],
            'errors': [f'Erro ao abrir XLSX: {str(e)}'],
            'sheet_names': [],
            'selected_sheet': None,
            'total_rows': 0,
        }

    sheet_names = xl.sheet_names

    # Auto-select the best sheet if not specified
    if not sheet_name:
        preferred = ['TESTE PLM', 'Compra Total']
        for pref in preferred:
            if pref in sheet_names:
                sheet_name = pref
                break
        if not sheet_name:
            sheet_name = sheet_names[0]

    if sheet_name not in sheet_names:
        return {
            'items': [],
            'errors': [f'Aba "{sheet_name}" não encontrada. Disponíveis: {sheet_names}'],
            'sheet_names': sheet_names,
            'selected_sheet': sheet_name,
            'total_rows': 0,
        }

    # Read the sheet
    df = pd.read_excel(xl, sheet_name=sheet_name, header=None, dtype=str)

    # Find the header row by looking for known column names
    header_row = _find_header_row(df)
    if header_row is None:
        return {
            'items': [],
            'errors': ['Não foi possível encontrar o cabeçalho do Excel.'],
            'sheet_names': sheet_names,
            'selected_sheet': sheet_name,
            'total_rows': 0,
        }

    # Set headers and slice data
    headers_raw = df.iloc[header_row].tolist()
    df_data = df.iloc[header_row + 1:].reset_index(drop=True)

    # Map headers to our internal field names
    col_mapping = {}  # Excel col index → internal field name
    mapped_headers = []
    for idx, h in enumerate(headers_raw):
        norm = _normalize_header(h) if pd.notna(h) else ''
        field = _COL_MAP.get(norm)
        if field:
            col_mapping[idx] = field
            mapped_headers.append(field)
        else:
            mapped_headers.append(None)

    # Parse rows into items
    items = []
    skipped = 0
    for row_idx in range(len(df_data)):
        row = df_data.iloc[row_idx]
        item = {}
        for col_idx, field_name in col_mapping.items():
            if field_name in _SKIP_FIELDS:
                continue
            val = row.iloc[col_idx] if col_idx < len(row) else None
            if pd.notna(val):
                val_str = str(val).strip()
                # Skip formula errors
                if val_str in ('#VALUE!', '#REF!', '#N/A', '#DIV/0!', '#NAME?'):
                    continue
                item[field_name] = val_str

        # Skip empty rows (must have at least some identifying info)
        if not item.get('referencia') and not item.get('sub_group') and not item.get('supplier'):
            skipped += 1
            continue

        # Build pilot_size from size columns
        sizes = []
        for size_field, size_label in _SIZE_COLS:
            qty = item.pop(size_field, None)
            if qty and qty not in ('0', '0.0', ''):
                sizes.append(f'{size_label}({qty})')
        if sizes:
            item['pilot_size'] = ', '.join(sizes)

        # Clean delivery_date
        if 'delivery_date' in item:
            dd = item['delivery_date']
            if ' 00:00:00' in dd:
                item['delivery_date'] = dd.replace(' 00:00:00', '')

        # Build a display reference for preview table
        parts = []
        if item.get('sub_group'):
            parts.append(item['sub_group'])
        if item.get('referencia'):
            parts.append(item['referencia'])
        if item.get('colors'):
            parts.append(item['colors'])
        if item.get('supplier'):
            parts.append(f"({item['supplier']})")
        item['_display_ref'] = ' - '.join(parts) if parts else f'Linha {row_idx + 1}'
        item['_row_number'] = row_idx + header_row + 2  # 1-based Excel row

        items.append(item)

    logger.info(
        'parse_compras_xlsx: sheet=%s header_row=%d items=%d skipped=%d',
        sheet_name, header_row, len(items), skipped
    )

    return {
        'items': items,
        'sheet_names': sheet_names,
        'selected_sheet': sheet_name,
        'total_rows': len(items),
        'skipped_rows': skipped,
        'mapped_columns': list(set(col_mapping.values()) - _SKIP_FIELDS),
        'errors': [],
    }


def _find_header_row(df, max_rows=5):
    """
    Find the header row by looking for known column names.
    Searches the first `max_rows` rows.
    """
    known = {'referência', 'referencia', 'artigo', 'composição', 'composicao',
             'grupo', 'subgrupo', 'fornecedor', 'cor', 'linha', 'corner',
             'composição ', 'preço de venda', 'preco de venda', 'coleção'}

    best_row = None
    best_count = 0

    for row_idx in range(min(max_rows, len(df))):
        row_vals = df.iloc[row_idx].tolist()
        count = 0
        for v in row_vals:
            if pd.notna(v) and _normalize_header(v) in known:
                count += 1
        if count > best_count:
            best_count = count
            best_row = row_idx

    # Need at least 3 known columns to be confident
    if best_count >= 3:
        return best_row
    return None
