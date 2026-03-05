"""
Fluxogama Retorno (consulta) — buscar modelo por referência.

Usa /retorno/modelo para consultar se um modelo já existe no Fluxogama
pela referência (ds_referencia). Retorna o modelo.id se encontrado.
"""
import json
import os
import ssl
import urllib.request
import urllib.error


def buscar_modelo_por_referencia(referencia: str) -> int | None:
    """
    Busca um modelo no Fluxogama pela referência.
    
    Usa filtro %like% no modelo.ds_referencia para cobrir casos como:
    - "S27TH033" (exato)
    - "CAMISETA DOG JADORE - S27TH033" (nome + ref)
    
    Returns:
        modelo.id (int) se encontrado, None se não existe.
    """
    if not referencia or not referencia.strip():
        return None

    # Get fresh token via token_manager
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

    # Formato correto: campos.campos (plural) + campo/operador/valor
    body_data = {
        "pagina": 1,
        "campos": {
            "campos": [
                "modelo.id",
                "modelo.ds_referencia",
                "modelo.ws_id"
            ]
        },
        "filtros": [
            {
                "campo": "modelo.ds_referencia",
                "operador": "%like%",
                "valor": ref_clean
            }
        ]
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

            if not isinstance(data, dict):
                print(f"  [RETORNO] Resposta inesperada: {type(data)}")
                return None

            dados = data.get('dados', [])
            if not dados:
                print(f"  [RETORNO] Nenhum modelo encontrado para ref '{ref_clean}'")
                return None

            # Se múltiplos resultados, filtrar pelo match mais específico
            if len(dados) == 1:
                modelo_id = dados[0].get('modelo.id')
                ds_ref = dados[0].get('modelo.ds_referencia', '')
                print(f"  [RETORNO] ✅ Match único: id={modelo_id} | ref='{ds_ref}'")
                return int(modelo_id) if modelo_id else None

            # Múltiplos resultados — buscar match exato na parte final
            for item in dados:
                ds_ref = item.get('modelo.ds_referencia', '')
                # Extrai sufixo: "CAMISETA DOG JADORE - S27TH033" → "S27TH033"
                ref_parts = ds_ref.rsplit(' - ', 1)
                ref_suffix = ref_parts[-1].strip() if ref_parts else ds_ref.strip()
                
                if ref_suffix.upper() == ref_clean.upper() or ds_ref.upper() == ref_clean.upper():
                    modelo_id = item.get('modelo.id')
                    print(f"  [RETORNO] ✅ Match exato: id={modelo_id} | ref='{ds_ref}' (de {len(dados)} resultados)")
                    return int(modelo_id) if modelo_id else None

            # Nenhum match exato, pegar o primeiro
            modelo_id = dados[0].get('modelo.id')
            ds_ref = dados[0].get('modelo.ds_referencia', '')
            print(f"  [RETORNO] ⚠️ {len(dados)} resultados, usando primeiro: id={modelo_id} | ref='{ds_ref}'")
            return int(modelo_id) if modelo_id else None

    except urllib.error.HTTPError as e:
        err = ''
        try:
            err = e.read().decode('utf-8')[:200]
        except Exception:
            pass
        print(f"  [RETORNO] ❌ HTTP {e.code}: {err}")
        return None
    except Exception as e:
        print(f"  [RETORNO] ❌ Erro: {e}")
        return None
