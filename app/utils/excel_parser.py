import io
import re
import math
import unicodedata
import logging
import pandas as pd

logger = logging.getLogger('excel_parser')

# Values treated as empty / missing
_EMPTY_MARKERS = {'', 'n/a', 'na', 'n.a.', '-', '—', '–', 'none', 'null', 'undefined'}

HEADER_FIELD_MAP = {
    'proforma_invoice': 'proforma_invoice',
    'number_pi_order': 'number_pi_order',
    'supplier_no': 'supplier_no',
    'buyer_importer': 'buyer_importer',
    'manufacturer_exporter': 'manufacturer_exporter',
    'order_information': 'order_information',
    'name_company': 'name_company',
    'adress': 'adress',
    'city': 'city',
    'state_province': 'state_province',
    'country': 'country',
    'tel_fax': 'tel_fax',
    'contact_name': 'contact_name',
    'e_mail': 'e_mail',
    'order_date': 'order_date',
    'production_time': 'production_time',
    'shipment_date': 'shipment_date',
    'terms_of_payment': 'terms_of_payment',
    'incoterm': 'incoterm',
    'shipment_port': 'shipment_port',
    'destination_port': 'destination_port',
    'bank_information': 'bank_information',
    'beneficiary': 'beneficiary',
    'beneficiary_adress': 'beneficiary_adress',
    'advising_bank': 'advising_bank',
    'swift_code': 'swift_code',
    'bank_adress': 'bank_adress',
    'account': 'account',
    'packing_information': 'packing_information',
    'total_of_package_s': 'total_of_package_s',
    'type_of_package': 'type_of_package',
    'dimensions_of_pack': 'dimensions_of_pack',
    'total_gross_weight': 'total_gross_weight',
    'total_net_weight': 'total_net_weight',
    'total_cbm': 'total_cbm',
    'information_oaz_comercial_ltda': 'information_oaz_comercial_ltda',
}

COLUMN_MAP = {
    'img_ref': 'img_ref',
    'item_no_ref_supplier': 'item_no_ref_supplier',
    'item_no_ref_supplier_': 'item_no_ref_supplier',
    'item_no_ref_supplier_ref_supplier': 'item_no_ref_supplier',
    'material_composition_percentage': 'material_composition_percentage',
    'color': 'color',
    'portuguese_description': 'description_item',
    'description_item': 'description_item',
    'ncm': 'ncm',
    'changes_by_oaz': 'changes_by_oaz',
    'oaz_reference': 'oaz_reference',
    'care_instructions': 'care_instructions',
    'label': 'label',
    'length_cm': 'length_cm',
    'width_cm': 'width_cm',
    'height_cm': 'height_cm',
    'diameter_cm': 'diameter_cm',
    'unit_net_weight_kg': 'unit_net_weight_kg',
    'moq': 'moq',
    'order_qty': 'oaz_qty',
    'oaz_qty': 'oaz_qty',
    'inner_packing_pcs': 'inner_packing_pcs',
    'outer_packing_pcs': 'outer_packing_pcs',
    'cbm': 'cbm',
    'packing': 'packing',
    'unit_price': 'unit_price',
    'total_amount': 'total_amount',
    'preco_r': 'preco_r',
    'atacado': 'atacado',
    'familia': 'familia',
    'entrada': 'entrada',
    'linha': 'linha',
    'grupo': 'grupo',
    'sub_grupo': 'sub_grupo',
    'nome_desc_produto': 'nome_desc_produto',
    'cor_sistema': 'cor_sistema',
    'material_obs_linx': 'material_obs_ns',
    'material_obs_ns': 'material_obs_ns',
    'obs': 'obs',
    'samples_qty': 'pp_samples_qty',
    'repeat_recompra': 'repeat_recompra',
    'colecao': 'colecao',
    'colecao_': 'colecao',
    'collection': 'colecao',
}

NUMERIC_FIELDS = {
    'length_cm',
    'width_cm',
    'height_cm',
    'diameter_cm',
    'unit_net_weight_kg',
    'moq',
    'oaz_qty',
    'inner_packing_pcs',
    'outer_packing_pcs',
    'cbm',
    'unit_price',
    'total_amount',
    'preco_r',
    'atacado',
    'pp_samples_qty',
}


def strip_accents(text):
    if not isinstance(text, str):
        return text
    normalized = unicodedata.normalize('NFKD', text)
    return ''.join([c for c in normalized if not unicodedata.combining(c)])


def normalize_column_name(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    text = strip_accents(str(value))
    text = text.strip().lower().replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
    return text


def parse_number(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = strip_accents(str(value)).strip()
    if not text or text.lower() in _EMPTY_MARKERS:
        return None
    text = text.replace(' ', '')
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return float(text)
    except ValueError:
        return None


def clean_string(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() in _EMPTY_MARKERS:
        return None
    return text


def _find_header_row(df):
    max_rows = min(200, len(df))
    best_row = None
    best_score = -1

    for i in range(max_rows):
        row = df.iloc[i].tolist()
        normalized = [normalize_column_name(v) for v in row if pd.notna(v)]
        if not normalized:
            continue
        mapped = sum(1 for name in normalized if name in COLUMN_MAP)
        score = mapped * 10 + len(normalized)
        if mapped >= 3 and score > best_score:
            best_score = score
            best_row = i

    if best_row is not None:
        return best_row

    max_count = 0
    fallback = None
    for i in range(max_rows):
        count = df.iloc[i].notna().sum()
        if count > max_count:
            max_count = count
            fallback = i
    return fallback


def extract_header_metadata(df, header_row):
    header_raw = []
    header_data = {}

    for i in range(header_row):
        row = df.iloc[i].tolist()
        non_empty = [(idx, val) for idx, val in enumerate(row) if pd.notna(val)]
        if not non_empty:
            continue

        header_raw.append({
            'row': i,
            'values': [clean_string(val) if pd.notna(val) else None for val in row],
        })

        for idx, val in non_empty:
            label = clean_string(val)
            if not label:
                continue
            next_value = None
            for j in range(idx + 1, len(row)):
                if pd.notna(row[j]):
                    next_value = clean_string(row[j])
                    break
            if next_value is None:
                continue
            normalized = normalize_column_name(label)
            field = HEADER_FIELD_MAP.get(normalized)
            if field and not header_data.get(field):
                header_data[field] = next_value

    return header_data, header_raw


# Columns that MUST exist for a row to be valid
_REQUIRED_COLUMNS = {'item_no_ref_supplier'}
# Columns that are optional — default to 0 if missing or empty
_OPTIONAL_NUMERIC_DEFAULTS = {'moq': 0, 'oaz_qty': 0}
# All expected columns (for warning generation)
_EXPECTED_COLUMNS = {'item_no_ref_supplier', 'moq', 'oaz_qty'}

_MAX_INVALID_SAMPLES = 20


def parse_excel(file_bytes):
    stream = io.BytesIO(file_bytes)
    xl = pd.ExcelFile(stream, engine='openpyxl')
    sheet = 'SOUQ' if 'SOUQ' in xl.sheet_names else xl.sheet_names[0]
    df_raw = xl.parse(sheet_name=sheet, header=None)

    header_row = _find_header_row(df_raw)
    if header_row is None:
        return {
            'header': {},
            'header_raw': [],
            'columns': [],
            'items': [],
            'invalid_rows': [],
            'warnings': [],
            'errors': ['header_row_not_found'],
            'messages': [{'severity': 'error', 'text': 'Linha de cabeçalho não encontrada.'}],
        }

    header_values = df_raw.iloc[header_row].tolist()
    columns = []
    seen = {}

    for idx, value in enumerate(header_values):
        source_name = clean_string(value) or ''
        normalized = normalize_column_name(value)
        mapped = COLUMN_MAP.get(normalized, normalized)
        if not mapped:
            mapped = f"col_{idx}"
        if mapped in seen:
            seen[mapped] += 1
            mapped = f"{mapped}_{seen[mapped]}"
        else:
            seen[mapped] = 1
        columns.append({
            'index': idx,
            'sourceColumnName': source_name,
            'name': mapped,
        })

    # ── Log & check detected columns ─────────────────────────────────
    mapped_names = {c['name'] for c in columns}
    detected_in_map = {c['name'] for c in columns if c['name'] in COLUMN_MAP.values()}
    unmapped_cols = [c for c in columns if c['name'] not in COLUMN_MAP.values()]
    missing_expected = _EXPECTED_COLUMNS - mapped_names
    missing_required = _REQUIRED_COLUMNS - mapped_names

    logger.info(
        'parse_excel: sheet=%s header_row=%d total_cols=%d mapped=%d unmapped=%d | '
        'mapped_names=%s | missing_expected=%s',
        sheet, header_row, len(columns), len(detected_in_map),
        len(unmapped_cols), sorted(detected_in_map), sorted(missing_expected),
    )
    if unmapped_cols:
        logger.debug(
            'Unmapped columns: %s',
            [(c['sourceColumnName'], c['name']) for c in unmapped_cols],
        )

    # ── Build structured messages ────────────────────────────────────
    messages = []
    errors = []
    warnings = []

    # CRITICAL: if required column (item_no_ref_supplier) is completely missing
    if missing_required:
        for mc in sorted(missing_required):
            msg = f'Coluna obrigatória "{mc}" não encontrada no cabeçalho. Importação impossível.'
            messages.append({'severity': 'error', 'text': msg})
            errors.append(msg)

    # WARNING: optional columns missing
    missing_optional = missing_expected - _REQUIRED_COLUMNS
    if missing_optional:
        for mc in sorted(missing_optional):
            default = _OPTIONAL_NUMERIC_DEFAULTS.get(mc, 0)
            msg = f'Coluna "{mc}" ausente — usando default {default}.'
            messages.append({'severity': 'warning', 'text': msg})
            warnings.append(msg)

    # If required columns are missing, we can still parse but all rows will be invalid
    # Return early with error if item_no column doesn't exist at all
    if missing_required:
        return {
            'header': {},
            'header_raw': [],
            'columns': columns,
            'items': [],
            'invalid_rows': [],
            'warnings': warnings,
            'errors': errors,
            'messages': messages,
            'detected_columns': sorted(detected_in_map),
            'missing_columns': sorted(missing_expected),
            'unmapped_columns': [
                {'source': c['sourceColumnName'], 'mapped_as': c['name']}
                for c in unmapped_cols
            ],
        }

    header_data, header_raw = extract_header_metadata(df_raw, header_row)
    df = df_raw.iloc[header_row + 1:].copy()
    df.columns = [col['name'] for col in columns]

    items = []
    invalid_rows = []
    invalid_total = 0  # total count (may exceed _MAX_INVALID_SAMPLES)
    fractional_qty_rows = []  # rows where qty had fractional values

    # ── Integer qty fields (should be whole numbers) ──────────────
    _INTEGER_QTY_FIELDS = {'moq', 'oaz_qty', 'inner_packing_pcs', 'outer_packing_pcs'}

    for idx, row in df.iterrows():
        raw_row = {}
        item = {}

        for col_meta in columns:
            name = col_meta['name']
            source_name = col_meta['sourceColumnName'] or name
            value = row.get(name)
            raw_row[source_name] = clean_string(value) if pd.notna(value) else None

            if name in NUMERIC_FIELDS:
                item[name] = parse_number(value)
            else:
                item[name] = clean_string(value)

        item_no = (item.get('item_no_ref_supplier') or '').strip()

        # Apply defaults for optional numeric fields
        for field, default_val in _OPTIONAL_NUMERIC_DEFAULTS.items():
            if item.get(field) is None:
                item[field] = default_val

        moq = item.get('moq')
        oaz_qty = item.get('oaz_qty')

        # Skip completely empty rows
        if not item_no and moq == 0 and oaz_qty == 0:
            has_any_value = any(v for v in raw_row.values() if v)
            if not has_any_value:
                continue

        # Only item_no_ref_supplier is truly required per row
        if not item_no:
            invalid_total += 1
            if len(invalid_rows) < _MAX_INVALID_SAMPLES:
                invalid_rows.append({
                    'row': int(idx) + 1,
                    'errors': ['item_no_ref_supplier'],
                    'rawRow': raw_row,
                })
            continue

        # ── Qty normalization: float → int when whole ────────────
        for qf in _INTEGER_QTY_FIELDS:
            val = item.get(qf)
            if val is not None and isinstance(val, float):
                if val == int(val):
                    item[qf] = int(val)
                else:
                    # Fractional qty — round and warn
                    if len(fractional_qty_rows) < 5:
                        fractional_qty_rows.append({
                            'row': int(idx) + 1,
                            'field': qf,
                            'original': val,
                            'rounded': math.ceil(val),
                        })
                    item[qf] = math.ceil(val)

        item['raw_row'] = raw_row
        items.append(item)

    # ── Duplicate item_no detection ──────────────────────────────
    item_no_counts = {}
    for it in items:
        ref = it.get('item_no_ref_supplier', '')
        item_no_counts[ref] = item_no_counts.get(ref, 0) + 1
    duplicates = {k: v for k, v in item_no_counts.items() if v > 1}

    # ── Build messages for invalid rows (severity=error, not warning) ──
    if invalid_total > 0:
        example_rows = [str(ir['row']) for ir in invalid_rows[:5]]
        count_text = f'{invalid_total}' if invalid_total <= _MAX_INVALID_SAMPLES else f'{invalid_total}'
        msg = (
            f'{count_text} linha(s) sem item_no_ref_supplier — '
            f'estas linhas NÃO serão importadas '
            f'(ex. linhas: {", ".join(example_rows)})'
        )
        messages.append({'severity': 'error', 'text': msg})

    # ── Duplicates warning ───────────────────────────────────────
    if duplicates:
        dup_examples = list(duplicates.items())[:5]
        dup_text = ', '.join(f'"{k}" ({v}x)' for k, v in dup_examples)
        total_dups = sum(v - 1 for v in duplicates.values())
        msg = (
            f'{len(duplicates)} item_no duplicado(s) ({total_dups} linhas extras): '
            f'{dup_text}'
        )
        if len(duplicates) > 5:
            msg += f' ... +{len(duplicates) - 5} mais'
        messages.append({'severity': 'warning', 'text': msg})
        warnings.append(msg)

    # ── Fractional qty warning ───────────────────────────────────
    if fractional_qty_rows:
        frac_examples = ', '.join(
            f'linha {f["row"]}: {f["field"]}={f["original"]}→{f["rounded"]}'
            for f in fractional_qty_rows[:3]
        )
        msg = (
            f'{len(fractional_qty_rows)} valor(es) de quantidade fracionário(s) '
            f'arredondado(s): {frac_examples}'
        )
        messages.append({'severity': 'warning', 'text': msg})
        warnings.append(msg)

    # ── Block import if 0 valid rows ─────────────────────────────
    if len(items) == 0 and not errors:
        msg = 'Nenhuma linha válida encontrada. Importação impossível.'
        messages.append({'severity': 'error', 'text': msg})
        errors.append(msg)

    return {
        'header': header_data,
        'header_raw': header_raw,
        'columns': columns,
        'items': items,
        'invalid_rows': invalid_rows,
        'warnings': warnings,
        'errors': errors,
        'messages': messages,
        'detected_columns': sorted(detected_in_map),
        'missing_columns': sorted(missing_expected),
        'unmapped_columns': [
            {'source': c['sourceColumnName'], 'mapped_as': c['name']}
            for c in unmapped_cols
        ],
        'duplicates': duplicates,
        'counts_summary': {
            'valid': len(items),
            'invalid': invalid_total,
            'duplicated_refs': len(duplicates),
            'fractional_qty': len(fractional_qty_rows),
        },
    }

