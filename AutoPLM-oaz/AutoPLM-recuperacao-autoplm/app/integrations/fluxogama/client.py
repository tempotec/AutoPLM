"""
Fluxogama HTTP Client
=====================
Sends payloads to the Fluxogama API using urllib (no external dependencies).
Supports dry-run mode for testing without actually sending.
"""
import json
import logging
import os
import ssl
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

logger = logging.getLogger('fluxogama.client')


def _get_config():
    """Read Fluxogama config from environment variables.
    Supports both OAZ_* (current .env) and FLUXOGAMA_* (legacy) prefixes.
    Uses token_manager.get_token() to ensure auto-renewal of expired tokens.
    """
    base_url = (os.environ.get('OAZ_BASE_URL') or os.environ.get('FLUXOGAMA_BASE_URL', '')).rstrip('/')
    
    # Try to get a fresh token via token_manager (auto-renews if expired)
    chave = None
    try:
        from app.integrations.fluxogama.token_manager import get_token
        chave = get_token()
    except Exception:
        pass
    # Fallback to env var if token_manager not available
    if not chave:
        chave = os.environ.get('OAZ_CHAVE') or os.environ.get('FLUXOGAMA_CHAVE', '')
    
    endpoint = os.environ.get('OAZ_MODELO_PUSH_PATH') or os.environ.get('FLUXOGAMA_ENDPOINT_ENVIO', '/remessa/envio')
    return base_url, chave, endpoint


def send_payload(payload, dry_run=False):
    """
    Send a payload to the Fluxogama API.

    Args:
        payload: dict with the Fluxogama fields
        dry_run: if True, returns the payload without sending

    Returns:
        dict with keys:
            - status: 'dry_run' | 'success' | 'error'
            - payload: the payload that was (or would be) sent
            - response: API response body (if sent)
            - http_status: HTTP status code (if sent)
            - error: error message (if error)
            - timestamp: ISO timestamp
    """
    timestamp = datetime.utcnow().isoformat() + 'Z'

    if dry_run:
        return {
            'status': 'dry_run',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': None,
            'timestamp': timestamp,
        }

    base_url, chave, endpoint = _get_config()

    # Validate config
    if not base_url:
        return {
            'status': 'error',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': 'FLUXOGAMA_BASE_URL não configurada no .env',
            'timestamp': timestamp,
        }
    if not chave:
        return {
            'status': 'error',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': 'FLUXOGAMA_CHAVE não configurada no .env',
            'timestamp': timestamp,
        }

    # Build URL (no more chave in query string)
    url = f"{base_url}{endpoint}"

    # Wrap payload in array — Fluxogama API expects ArrayList<Modelo>
    body = json.dumps([payload], ensure_ascii=False).encode('utf-8')

    # Build request with Bearer token auth
    req = urllib.request.Request(
        url,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            'User-Agent': 'OAZ-StyleSheet-PLM/1.0',
            'Authorization': f'Bearer {chave}',
        },
    )

    # Create SSL context (allow self-signed in dev if needed)
    ctx = ssl.create_default_context()

    logger.info(
        "Fluxogama POST %s | payload_size=%d bytes | ws_id=%s",
        url, len(body), payload.get('ws_id', '?'),
    )
    t0 = time.monotonic()

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            elapsed = time.monotonic() - t0
            http_status = resp.status
            response_body = resp.read().decode('utf-8')
            try:
                response_data = json.loads(response_body)
            except (ValueError, TypeError):
                response_data = response_body

            logger.info(
                "Fluxogama OK | status=%d | elapsed=%.2fs | response_size=%d",
                http_status, elapsed, len(response_body),
            )

            return {
                'status': 'success',
                'payload': payload,
                'response': response_data,
                'http_status': http_status,
                'error': None,
                'timestamp': timestamp,
            }
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - t0
        error_body = ''
        try:
            error_body = e.read().decode('utf-8')
        except Exception:
            pass

        logger.error(
            "Fluxogama HTTP ERROR | status=%d %s | elapsed=%.2fs | body=%s",
            e.code, e.reason, elapsed, error_body[:500],
        )

        return {
            'status': 'error',
            'payload': payload,
            'response': error_body,
            'http_status': e.code,
            'error': f'HTTP {e.code}: {e.reason}',
            'timestamp': timestamp,
        }
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - t0
        logger.error(
            "Fluxogama URL ERROR | reason=%s | elapsed=%.2fs",
            str(e.reason), elapsed,
        )
        return {
            'status': 'error',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': f'Erro de conexão: {str(e.reason)}',
            'timestamp': timestamp,
        }
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error(
            "Fluxogama UNEXPECTED ERROR | type=%s | msg=%s | elapsed=%.2fs",
            type(e).__name__, str(e), elapsed,
        )
        return {
            'status': 'error',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': f'Erro inesperado: {str(e)}',
            'timestamp': timestamp,
        }
