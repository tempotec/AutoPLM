"""
Fluxogama Token Manager
========================
Automatically renews the Fluxogama JWT token before it expires.
Runs a background daemon thread that checks every 5 minutes if the
token is within 1 hour of expiry, and renews it proactively.

Usage:
    from app.integrations.fluxogama.token_manager import get_token, start_auto_renewal

    # Call once at app startup:
    start_auto_renewal()

    # Then anywhere you need the token:
    token = get_token()
"""
import base64
import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger('fluxogama.token_manager')

# In-memory state
_lock = threading.Lock()
_current_token: str = ''
_token_exp: float = 0  # Unix timestamp of expiry
_renewal_thread: threading.Thread | None = None

# How early to renew before expiry (seconds)
RENEW_AHEAD_SECS = 3600  # 1 hour
# How often the background thread checks (seconds)
CHECK_INTERVAL_SECS = 300  # 5 minutes


def _decode_jwt_exp(token: str) -> float:
    """Extract 'exp' from a JWT without verifying signature."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return 0
        # Decode the payload (part 1), adding padding as needed
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload.get('exp', 0))
    except Exception as e:
        logger.warning("Não foi possível decodificar JWT: %s", e)
        return 0


def _time_until_expiry(token: str) -> float:
    """Returns seconds until token expires. Negative = already expired."""
    exp = _decode_jwt_exp(token)
    if exp == 0:
        return -1
    return exp - time.time()


def _authenticate() -> str | None:
    """Call Fluxogama /autenticacao to get a fresh JWT token."""
    base_url = (os.environ.get('OAZ_BASE_URL') or '').rstrip('/')
    usuario = os.environ.get('OAZ_USUARIO', '')
    senha = os.environ.get('OAZ_SENHA', '')

    if not base_url or not usuario or not senha:
        logger.error(
            "[TOKEN] Credenciais incompletas: OAZ_BASE_URL=%s OAZ_USUARIO=%s OAZ_SENHA=%s",
            bool(base_url), bool(usuario), '***' if senha else 'VAZIO',
        )
        return None

    url = f"{base_url}/autenticacao"
    body = json.dumps({
        "chave": 1,
        "usuario": usuario,
        "senha": senha,
    }).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'OAZ-TokenManager/1.0',
        },
    )

    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            token = None
            if isinstance(data, dict):
                # {sucesso: true, retorno: {token: "..."}}
                retorno = data.get('retorno', {})
                if isinstance(retorno, dict):
                    token = retorno.get('token')
                # Fallback: top-level token key
                if not token:
                    token = data.get('token')

            if token:
                ttl = _time_until_expiry(token)
                print(f"[TOKEN] ✅ Novo token obtido | expira em {ttl/3600:.1f}h ({_fmt_exp(token)})")
                logger.info("[TOKEN] Novo token obtido, expira em %.1fh", ttl / 3600)
                return token
            else:
                print(f"[TOKEN] ❌ Resposta sem token: {json.dumps(data)[:200]}")
                logger.error("[TOKEN] Resposta sem token: %s", json.dumps(data)[:200])
                return None
    except urllib.error.HTTPError as e:
        body_err = ''
        try:
            body_err = e.read().decode('utf-8')[:200]
        except Exception:
            pass
        print(f"[TOKEN] ❌ HTTP {e.code}: {body_err}")
        logger.error("[TOKEN] HTTP %d: %s", e.code, body_err)
        return None
    except Exception as e:
        print(f"[TOKEN] ❌ Erro na autenticação: {e}")
        logger.error("[TOKEN] Erro: %s", e)
        return None


def _fmt_exp(token: str) -> str:
    """Format expiry as human-readable datetime."""
    exp = _decode_jwt_exp(token)
    if exp == 0:
        return '?'
    return datetime.fromtimestamp(exp, tz=timezone.utc).strftime('%d/%m/%Y %H:%M UTC')


def get_token() -> str:
    """Get the current valid token. Renews if expired or about to expire."""
    global _current_token, _token_exp

    with _lock:
        # Check if current token is still valid (with margin)
        remaining = _token_exp - time.time()
        if _current_token and remaining > RENEW_AHEAD_SECS:
            return _current_token

    # Token expired or about to expire — try renewal
    _try_renew()

    with _lock:
        return _current_token


def _try_renew():
    """Attempt to renew the token."""
    global _current_token, _token_exp

    new_token = _authenticate()
    if new_token:
        exp = _decode_jwt_exp(new_token)
        with _lock:
            _current_token = new_token
            _token_exp = exp
            # Also update the env var so other parts of the app see it
            os.environ['OAZ_CHAVE'] = new_token
        return True
    else:
        # If renewal fails, keep using the old token
        logger.warning("[TOKEN] Renovação falhou, mantendo token atual")
        return False


def _background_loop():
    """Background thread that periodically checks and renews the token."""
    print(f"[TOKEN] 🔄 Background auto-renewal ativo (verifica a cada {CHECK_INTERVAL_SECS}s, renova {RENEW_AHEAD_SECS/3600:.0f}h antes)")

    while True:
        try:
            time.sleep(CHECK_INTERVAL_SECS)

            with _lock:
                remaining = _token_exp - time.time()
                has_token = bool(_current_token)

            if not has_token:
                print("[TOKEN] Sem token — tentando autenticar...")
                _try_renew()
            elif remaining <= RENEW_AHEAD_SECS:
                print(f"[TOKEN] Token expira em {remaining/60:.0f}min — renovando...")
                _try_renew()
            else:
                # Only log occasionally, not every check
                hours_left = remaining / 3600
                if int(hours_left * 60) % 30 == 0:  # ~every 30 min
                    logger.debug("[TOKEN] Token OK, expira em %.1fh", hours_left)
        except Exception as e:
            logger.error("[TOKEN] Erro no background loop: %s", e)
            time.sleep(60)  # Wait a bit before retrying


def start_auto_renewal():
    """Initialize the token manager and start the background renewal thread.
    Safe to call multiple times — only starts one thread.
    """
    global _renewal_thread, _current_token, _token_exp

    # Load initial token from env
    initial_token = os.environ.get('OAZ_CHAVE') or os.environ.get('FLUXOGAMA_CHAVE', '')

    if initial_token:
        exp = _decode_jwt_exp(initial_token)
        remaining = exp - time.time() if exp else -1
        with _lock:
            _current_token = initial_token
            _token_exp = exp

        if remaining > 0:
            print(f"[TOKEN] Token carregado do .env | expira em {remaining/3600:.1f}h ({_fmt_exp(initial_token)})")
        else:
            print(f"[TOKEN] Token do .env já expirou — renovando agora...")
            _try_renew()
    else:
        print("[TOKEN] Nenhum token no .env — autenticando...")
        _try_renew()

    # Start background thread (daemon so it dies with the app)
    if _renewal_thread is None or not _renewal_thread.is_alive():
        _renewal_thread = threading.Thread(target=_background_loop, daemon=True, name='flux-token-renewal')
        _renewal_thread.start()
