"""
OAZ Payload Mapper
==================
Maps FichaTecnicaItem fields to OAZ uno.X payload format.
Resolves WSID values via OazValueMap table for 'Banco de Dados' fields.
"""
import unicodedata


# ── Declarative field mapping ──────────────────────────────────────────────
# model_field → uno.X key, with type annotation for validation
FIELD_MAP = {
    # Text fields (sent as-is)
    'description_item':                 {'uno': 'uno.1',   'type': 'text',  'label': 'Descrição título peça'},
    'item_no_ref_supplier':             {'uno': 'uno.16',  'type': 'text',  'label': 'Ref do Fornecedor'},
    'care_instructions':                {'uno': 'uno.307', 'type': 'text',  'label': 'Instruções de cuidados'},
    'obs':                              {'uno': 'uno.443', 'type': 'text',  'label': 'Observações'},
    'label':                            {'uno': 'uno.58',  'type': 'text',  'label': 'Observação Etiqueta'},

    # Numeric fields (sent as numbers)
    'length_cm':                        {'uno': 'uno.309', 'type': 'number', 'label': 'Comprimento (cm)'},
    'width_cm':                         {'uno': 'uno.310', 'type': 'number', 'label': 'Largura (cm)'},
    'height_cm':                        {'uno': 'uno.311', 'type': 'number', 'label': 'Altura (cm)'},
    'diameter_cm':                      {'uno': 'uno.312', 'type': 'number', 'label': 'Diâmetro (cm)'},
    'unit_net_weight_kg':               {'uno': 'uno.313', 'type': 'number', 'label': 'Peso líquido unitário'},
    'moq':                              {'uno': 'uno.328', 'type': 'number', 'label': 'MOQ'},
    'inner_packing_pcs':                {'uno': 'uno.315', 'type': 'number', 'label': 'Embalagem Interna (pcs)'},
    'outer_packing_pcs':                {'uno': 'uno.316', 'type': 'number', 'label': 'Embalagem Exterior (pcs)'},

    # DB fields (need WSID resolution)
    'linha':                            {'uno': 'uno.10',  'type': 'db', 'label': 'Linha'},
    'grupo':                            {'uno': 'uno.11',  'type': 'db', 'label': 'Grupo'},
    'sub_grupo':                        {'uno': 'uno.12',  'type': 'db', 'label': 'Sub Grupo'},
    'material_composition_percentage':  {'uno': 'uno.24',  'type': 'db', 'label': 'Material Principal'},
    'ncm':                              {'uno': 'uno.50',  'type': 'db', 'label': 'NCM'},
    'familia':                          {'uno': 'uno.300', 'type': 'db', 'label': 'Família'},
}

# DB fields that MUST be resolved to WSID before push
DB_FIELDS = {k: v for k, v in FIELD_MAP.items() if v['type'] == 'db'}


def _strip_accents(text):
    """Remove accents for normalized matching."""
    if not isinstance(text, str):
        return str(text) if text is not None else ''
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text):
    """Normalize text for WSID lookup: strip accents, uppercase, trim."""
    if text is None:
        return ''
    return _strip_accents(str(text)).strip().upper()


def _first(*values):
    """Return the first non-empty value."""
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def resolve_wsid(field_key, text_value, oaz_map_lookup):
    """
    Look up a WSID for a given field_key + text_value.

    Args:
        field_key: e.g. "uno.10"
        text_value: e.g. "ACESSÓRIOS"
        oaz_map_lookup: dict of {(field_key, text_norm): wsid_value}

    Returns:
        (wsid_value, resolved) tuple
    """
    if text_value is None:
        return None, False
    text_norm = normalize_text(text_value)
    key = (field_key, text_norm)
    wsid = oaz_map_lookup.get(key)
    if wsid is not None:
        return wsid, True
    return text_value, False


def build_oaz_payload(ficha, item, oaz_map_lookup=None):
    """
    Build the OAZ /remessa/modelo payload from FichaTecnica + FichaTecnicaItem.

    Args:
        ficha: FichaTecnica instance (header)
        item: FichaTecnicaItem instance
        oaz_map_lookup: dict of {(field_key, text_norm): wsid_value}

    Returns:
        dict: {payload, errors, warnings, _fallbacks}
    """
    if oaz_map_lookup is None:
        oaz_map_lookup = {}

    errors = []
    warnings = []
    fallbacks = []
    payload = {}

    # ── referencia ──────────────────────────────────────────────────────
    referencia = _first(
        getattr(item, 'oaz_reference', None),
        getattr(item, 'item_no_ref_supplier', None),
    )
    if referencia and referencia != getattr(item, 'oaz_reference', None):
        fallbacks.append('referencia')
        warnings.append(
            "Usando 'Ref. Fornecedor' como fallback para a Referência OAZ."
        )
    if not referencia:
        errors.append("Falta 'referencia' (oaz_reference no item)")
    payload['referencia'] = referencia or ''

    # ── ws_id (internal identifier) ────────────────────────────────────
    payload['ws_id'] = f"ficha:{ficha.id}|item:{item.id}"

    # ── colecao ────────────────────────────────────────────────────────
    colecao = _first(
        getattr(item, 'colecao', None),
        getattr(ficha, 'proforma_invoice', None),
    )
    if colecao:
        payload['colecao'] = colecao

    # ── cores ──────────────────────────────────────────────────────────
    cor_value = _first(
        getattr(item, 'cor_sistema', None),
        getattr(item, 'color', None),
    )
    if cor_value:
        payload['cores'] = [{'cor': cor_value, 'variante': 1}]
    else:
        payload['cores'] = [{'cor': 'UNICA', 'variante': 1}]
        fallbacks.append('cor')
        warnings.append(
            "Cor não encontrada. Usando valor padrão 'UNICA'. Recomendado revisar variantes."
        )

    # ── uno.1 (Descrição) with fallback chain ──────────────────────────
    desc = _first(
        getattr(item, 'description_item', None),
        getattr(item, 'nome_desc_produto', None),
        getattr(item, 'item_no_ref_supplier', None),
    )
    if desc and desc != getattr(item, 'description_item', None):
        fallbacks.append('uno.1')
        warnings.append(f"Usando fallback para Descrição: '{desc}'")
    if not desc:
        errors.append("Falta 'uno.1' (Descrição do item)")
    payload['uno.1'] = desc or ''

    # ── Map remaining fields ───────────────────────────────────────────
    for model_field, cfg in FIELD_MAP.items():
        uno_key = cfg['uno']
        field_type = cfg['type']
        label = cfg['label']

        # Skip uno.1 (already handled above)
        if uno_key == 'uno.1':
            continue

        value = getattr(item, model_field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            # Optional field not filled
            if field_type == 'db' and uno_key in ('uno.10', 'uno.11', 'uno.12', 'uno.24'):
                warnings.append(
                    f"Campo '{uno_key}' ({label}) não preenchido."
                )
            continue

        if field_type == 'db':
            # Resolve WSID
            wsid, resolved = resolve_wsid(uno_key, value, oaz_map_lookup)
            if resolved:
                payload[uno_key] = wsid
            else:
                payload[uno_key] = value  # keep text for preview
                errors.append(
                    f"Campo '{uno_key}' ({label}) não resolvido para WSID "
                    f"(valor: '{value}'). Cadastre no De/Para."
                )
        elif field_type == 'number':
            payload[uno_key] = value
        else:
            # text
            payload[uno_key] = str(value)

    # ── Metadata (not sent to OAZ, not in hash) ───────────────────────
    payload['_fallbacks'] = fallbacks
    payload['_warnings'] = warnings
    payload['_errors'] = errors

    return {
        'payload': payload,
        'errors': errors,
        'warnings': warnings,
        'fallbacks': fallbacks,
    }


def get_oaz_map_lookup(db_session):
    """
    Build the WSID lookup dict from OazValueMap table.
    Returns: {(field_key, text_norm): wsid_value}
    """
    from app.models.oaz_value_map import OazValueMap
    maps = db_session.query(OazValueMap).all()
    return {(m.field_key, m.text_norm): m.wsid_value for m in maps}
