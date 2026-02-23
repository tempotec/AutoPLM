"""
OAZ HTTP Client
===============
Connects to the Fluxogama/OAZ API (/remessa/modelo) using httpx.
Includes retry logic (tenacity) and schema caching.
"""
import hashlib
import json
import logging
import os
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

# In-memory schema cache
_schema_cache = {
    'data': None,
    'fetched_at': 0,
    'ttl': 900,  # 15 minutes
}

PLACEHOLDER_KEY = 'SUA_CHAVE_AQUI'


def _is_retryable(exc):
    """Retry on 429 (rate limit) and 5xx server errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout)):
        return True
    return False


class OazConfigError(RuntimeError):
    pass


class OazClient:
    def __init__(self, base_url=None, chave=None, timeout_s=30):
        self.base_url = (base_url or os.environ.get('OAZ_BASE_URL', '')).rstrip('/')
        self.chave = chave or os.environ.get('OAZ_CHAVE', '')

        if not self.base_url:
            raise OazConfigError('OAZ_BASE_URL não configurado no .env')
        if not self.chave:
            raise OazConfigError('OAZ_CHAVE não configurado no .env')
        if self.chave == PLACEHOLDER_KEY:
            raise OazConfigError(
                'OAZ_CHAVE ainda é o placeholder. Configure a chave real no .env'
            )

        self._client = httpx.Client(timeout=timeout_s)

    def _build_url(self, path):
        if path.startswith('http://') or path.startswith('https://'):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _safe_log_key(self):
        """Truncate key for logging (never log full key)."""
        if len(self.chave) > 12:
            return self.chave[:6] + '...' + self.chave[-4:]
        return '***'

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _request(self, method, path, params=None, json_data=None):
        params = dict(params or {})
        params['chave'] = self.chave

        url = self._build_url(path)

        logger.info(
            'OAZ %s %s (key=%s)',
            method, path, self._safe_log_key()
        )

        resp = self._client.request(method, url, params=params, json=json_data)
        resp.raise_for_status()

        try:
            return resp.json()
        except Exception:
            return {'raw': resp.text}

    def get_schema(self, schema_path=None):
        """Fetch the model schema from OAZ, with in-memory caching."""
        now = time.time()
        if (
            _schema_cache['data'] is not None
            and (now - _schema_cache['fetched_at']) < _schema_cache['ttl']
        ):
            return _schema_cache['data']

        path = schema_path or os.environ.get(
            'OAZ_MODELO_PUSH_PATH', '/remessa/modelo'
        )
        data = self._request('GET', path)
        _schema_cache['data'] = data
        _schema_cache['fetched_at'] = now
        logger.info('OAZ schema cached (%d keys)', len(data) if isinstance(data, dict) else 0)
        return data

    def push_modelo(self, payload, push_path=None):
        """POST a modelo payload to OAZ."""
        path = push_path or os.environ.get(
            'OAZ_MODELO_PUSH_PATH', '/remessa/modelo'
        )
        return self._request('POST', path, json_data=payload)


def compute_payload_hash(payload):
    """
    Compute a canonical SHA-256 hash of the payload.
    Excludes internal metadata (_fallbacks, _warnings) from the hash.
    """
    clean = {k: v for k, v in payload.items() if not k.startswith('_')}
    canonical = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
