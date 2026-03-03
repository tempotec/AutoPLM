"""
OAZ Payload Validator
=====================
Pre-flight validation for OAZ payloads.
Differentiates ERROR (blocks push) from WARNING (informational).
"""


def validate_oaz_payload(payload):
    """
    Validate a payload built by the mapper.

    Returns:
        dict with keys: ok (bool), errors (list), warnings (list)
    """
    errors = list(payload.get('_errors', []))
    warnings = list(payload.get('_warnings', []))

    # ── Required fields ────────────────────────────────────────────────
    referencia = payload.get('referencia')
    if not referencia or not str(referencia).strip():
        if "Falta 'referencia'" not in ' '.join(errors):
            errors.append("Falta 'referencia' (oaz_reference no item)")

    desc = payload.get('uno.1')
    if not desc or not str(desc).strip():
        if "Falta 'uno.1'" not in ' '.join(errors):
            errors.append("Falta 'uno.1' (Descrição do item)")

    cores = payload.get('cores', [])
    if not cores:
        warnings.append('Sem cores cadastradas')

    return {
        'ok': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
    }
