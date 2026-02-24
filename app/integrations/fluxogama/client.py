"""
Fluxogama HTTP Client
=====================
Sends payloads to the Fluxogama API using urllib (no external dependencies).
Supports dry-run mode for testing without actually sending.
"""
import json
import os
import ssl
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime


def _get_config():
    """Read Fluxogama config from environment variables."""
    base_url = os.environ.get('FLUXOGAMA_BASE_URL', '').rstrip('/')
    chave = os.environ.get('FLUXOGAMA_CHAVE', '')
    endpoint = os.environ.get('FLUXOGAMA_ENDPOINT_ENVIO', '/rest/api/v1/remessa/envio')
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

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            http_status = resp.status
            response_body = resp.read().decode('utf-8')
            try:
                response_data = json.loads(response_body)
            except (ValueError, TypeError):
                response_data = response_body

            return {
                'status': 'success',
                'payload': payload,
                'response': response_data,
                'http_status': http_status,
                'error': None,
                'timestamp': timestamp,
            }
    except urllib.error.HTTPError as e:
        error_body = ''
        try:
            error_body = e.read().decode('utf-8')
        except Exception:
            pass

        return {
            'status': 'error',
            'payload': payload,
            'response': error_body,
            'http_status': e.code,
            'error': f'HTTP {e.code}: {e.reason}',
            'timestamp': timestamp,
        }
    except urllib.error.URLError as e:
        return {
            'status': 'error',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': f'Erro de conexão: {str(e.reason)}',
            'timestamp': timestamp,
        }
    except Exception as e:
        return {
            'status': 'error',
            'payload': payload,
            'response': None,
            'http_status': None,
            'error': f'Erro inesperado: {str(e)}',
            'timestamp': timestamp,
        }
