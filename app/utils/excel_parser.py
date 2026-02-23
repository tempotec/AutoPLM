import io
import re
import unicodedata
import pandas as pd

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
    if not text:
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
    return text if text else None


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

    header_data, header_raw = extract_header_metadata(df_raw, header_row)
    df = df_raw.iloc[header_row + 1:].copy()
    df.columns = [col['name'] for col in columns]

    items = []
    invalid_rows = []
    warnings = []

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

        item_no = item.get('item_no_ref_supplier')
        moq = item.get('moq')
        oaz_qty = item.get('oaz_qty')

        if not item_no and moq is None and oaz_qty is None:
            continue

        if not item_no or moq is None or oaz_qty is None:
            invalid_rows.append({
                'row': int(idx) + 1,
                'errors': [
                    'missing_item_no' if not item_no else None,
                    'missing_moq' if moq is None else None,
                    'missing_oaz_qty' if oaz_qty is None else None,
                ],
                'rawRow': raw_row,
            })
            continue

        item['raw_row'] = raw_row
        items.append(item)

    if invalid_rows:
        warnings.append('invalid_rows_found')

    return {
        'header': header_data,
        'header_raw': header_raw,
        'columns': columns,
        'items': items,
        'invalid_rows': invalid_rows,
        'warnings': warnings,
        'errors': [],
    }
