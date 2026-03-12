"""
Fluxogama Retorno (consulta) — buscar modelo por referência.

Usa /retorno/modelo para consultar se um modelo já existe no Fluxogama
pela referência (ds_referencia). Retorna o modelo.id se encontrado.

Estratégias de busca (em ordem):
1. Referência completa: "CARDIGÃ - MARROM"
2. Nome do produto (antes do ' - '): "CARDIGÃ"

Filtros de precisão:
- Filtra por coleção se informada
- Requer match exato ou ≤3 resultados ambíguos
- Se >3 resultados e nenhum match exato → pula com aviso
"""
import json
import os
import ssl
import urllib.request
import urllib.error

MAX_AMBIGUOUS = 3  # Se mais de N resultados sem match exato → pular


def _do_search(url, token, search_term, colecao=None):
    """Execute a search against /retorno/modelo. Returns list of dados."""
    filtros = [
        {
            "campo": "modelo.ds_referencia",
            "operador": "%like%",
            "valor": search_term
        }
    ]

    # Add collection filter if available
    if colecao:
        filtros.append({
            "campo": "colecao.id",
            "operador": "=",
            "valor": str(colecao)
        })

    body_data = {
        "pagina": 1,
        "campos": {
            "campos": [
                "modelo.id",
                "modelo.ds_referencia",
                "modelo.ws_id"
            ]
        },
        "filtros": filtros
    }

    body = json.dumps(body_data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {token}',
            'User-Agent': 'OAZ-Retorno/1.0',
        },
    )
    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if isinstance(data, dict):
                return data.get('dados', [])
    except urllib.error.HTTPError as e:
        err = ''
        try:
            err = e.read().decode('utf-8')[:200]
        except Exception:
            pass
        print(f"  [RETORNO] ❌ HTTP {e.code}: {err}")
    except Exception as e:
        print(f"  [RETORNO] ❌ Erro: {e}")
    return []


def _find_exact_match(dados, ref_clean):
    """
    From a list of dados, find an exact match.
    Returns (modelo_id, ds_ref) or (None, None).
    """
    ref_upper = ref_clean.upper()

    for item in dados:
        ds_ref = (item.get('modelo.ds_referencia') or '').strip()
        ds_upper = ds_ref.upper()

        # Exact match on full reference
        if ds_upper == ref_upper:
            return item.get('modelo.id'), ds_ref

        # Match on parts: "CARDIGA - MARROM" matches "CARDIGA"
        if ' - ' in ref_upper:
            name_part = ref_upper.split(' - ', 1)[0].strip()
            if ds_upper == name_part:
                return item.get('modelo.id'), ds_ref

        # Reverse: Fluxogama has "BLUSA - OFF WHITE", we search "BLUSA"
        if ' - ' in ds_upper:
            flux_parts = ds_upper.rsplit(' - ', 1)
            flux_name = flux_parts[0].strip()
            if flux_name == ref_upper:
                return item.get('modelo.id'), ds_ref

    return None, None


def _pick_model(dados, ref_clean, search_term):
    """
    Pick the best model from search results.
    Returns modelo_id or None. Skips if too ambiguous.
    """
    if not dados:
        return None

    count = len(dados)

    # 1 result → use it
    if count == 1:
        modelo_id = dados[0].get('modelo.id')
        ds_ref = dados[0].get('modelo.ds_referencia', '')
        print(f"  [RETORNO] ✅ Match único: id={modelo_id} | ref='{ds_ref}'")
        return int(modelo_id) if modelo_id else None

    # Multiple results → look for exact match first
    exact_id, exact_ref = _find_exact_match(dados, ref_clean)
    if exact_id:
        print(f"  [RETORNO] ✅ Match exato: id={exact_id} | ref='{exact_ref}' (de {count} resultados)")
        return int(exact_id)

    # No exact match → check ambiguity threshold
    if count > MAX_AMBIGUOUS:
        refs_preview = ', '.join(
            f"'{d.get('modelo.ds_referencia', '?')}'" for d in dados[:5]
        )
        print(f"  [RETORNO] ⚠️ AMBÍGUO: {count} resultados para '{search_term}' — PULANDO (refs: {refs_preview})")
        return None  # Too ambiguous, skip

    # ≤3 results, no exact match → use first with warning
    modelo_id = dados[0].get('modelo.id')
    ds_ref = dados[0].get('modelo.ds_referencia', '')
    print(f"  [RETORNO] ⚠️ {count} resultados, usando mais próximo: id={modelo_id} | ref='{ds_ref}'")
    return int(modelo_id) if modelo_id else None


def buscar_modelo_por_referencia(referencia: str, colecao: str = None) -> int | None:
    """
    Busca um modelo no Fluxogama pela referência.

    Estratégias de busca (em ordem):
    1. Referência completa + coleção: "CARDIGÃ - MARROM" na coleção 15
    2. Nome do produto + coleção: "CARDIGÃ" na coleção 15
    3. Referência completa sem filtro de coleção (fallback)
    4. Nome do produto sem filtro de coleção (fallback)

    Regras de precisão:
    - Match exato sempre é aceito
    - ≤3 resultados sem match exato → usa o primeiro com aviso
    - >3 resultados sem match exato → pula (muito ambíguo)

    Returns:
        modelo.id (int) se encontrado, None se não existe.
    """
    if not referencia or not referencia.strip():
        return None

    # Get fresh token
    token = None
    try:
        from app.integrations.fluxogama.token_manager import get_token
        token = get_token()
    except Exception:
        pass
    if not token:
        token = os.environ.get('OAZ_CHAVE') or os.environ.get('FLUXOGAMA_CHAVE', '')

    base_url = (os.environ.get('OAZ_BASE_URL') or '').rstrip('/')
    if not base_url or not token:
        print(f"  [RETORNO] Configuração incompleta (base_url={bool(base_url)}, token={bool(token)})")
        return None

    url = f"{base_url}/retorno/modelo"
    ref_clean = referencia.strip()

    # Build search terms
    search_terms = [ref_clean]
    if ' - ' in ref_clean:
        name_part = ref_clean.split(' - ', 1)[0].strip()
        if name_part and name_part != ref_clean:
            search_terms.append(name_part)

    # Phase 1: Search WITH collection filter (most precise)
    if colecao:
        for term in search_terms:
            label = 'ref completa' if term == ref_clean else 'nome do produto'
            print(f"  [RETORNO] Buscando por {label} + coleção {colecao}: '{term}'...")
            dados = _do_search(url, token, term, colecao=colecao)
            if dados:
                result = _pick_model(dados, ref_clean, term)
                if result:
                    return result

    # Phase 2: Fallback WITHOUT collection filter
    for term in search_terms:
        label = 'ref completa' if term == ref_clean else 'nome do produto'
        print(f"  [RETORNO] Buscando por {label} (sem filtro coleção): '{term}'...")
        dados = _do_search(url, token, term)
        if dados:
            result = _pick_model(dados, ref_clean, term)
            if result:
                return result

    print(f"  [RETORNO] ❌ Nenhum modelo encontrado para '{ref_clean}' após todas as tentativas")
    return None
