import json
import os
import time
import uuid
import logging
from typing import Optional

import requests
import certifi
import urllib3

from dotenv import load_dotenv

try:
    from .ai_prompt import build_gigachat_prompt
except Exception:
    try:
        from backend.ai_prompt import build_gigachat_prompt
    except Exception:
        try:
            from ai_prompt import build_gigachat_prompt
        except Exception:
            build_gigachat_prompt = None

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

ACCESS_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
API_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_CACHED_TOKEN = None
_TOKEN_EXPIRES_AT = 0.0

def _safe_post(url, **kwargs):
    kwargs2 = kwargs.copy()
    if 'verify' not in kwargs2:
        kwargs2['verify'] = certifi.where()
    try:
        return requests.post(url, **kwargs2)
    except requests.exceptions.SSLError:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        kwargs2['verify'] = False
        return requests.post(url, **kwargs2)

def get_token_from_env() -> Optional[dict]:
    auth_key = os.getenv('GIGACHAT_AUTHORIZATION_KEY')
    if not auth_key:
        return None
    try:
        rquid = str(uuid.uuid4())
        start = time.time()
        r = _safe_post(
            ACCESS_URL,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": rquid,
                "Authorization": f"Bearer {auth_key}"
            },
            data={"scope": "GIGACHAT_API_PERS"},
            timeout=(3, 7)
        )
        elapsed = time.time() - start
        if elapsed > 5:
            logger.warning('Slow token request: %.2fs', elapsed)
        if r.status_code != 200:
            logger.warning('Token request failed: %s', r.status_code)
            return None
        data = r.json()
        if isinstance(data, dict) and ('access_token' in data):
            return data
        return None
    except Exception as exc:
        logger.exception('get_token_from_env failed: %s', exc)
        return None

def _get_cached_token() -> Optional[str]:
    global _CACHED_TOKEN, _TOKEN_EXPIRES_AT
    now = time.time()
    if _CACHED_TOKEN and _TOKEN_EXPIRES_AT > now + 5:
        return _CACHED_TOKEN
    info = get_token_from_env()
    if not info:
        return None

    token = info.get('access_token') or info.get('token')
    expires = int(info.get('expires_in') or 3600)
    _CACHED_TOKEN = token
    _TOKEN_EXPIRES_AT = now + expires
    return _CACHED_TOKEN

def _extract_content_from_response(r):
    try:
        data = r.json()
    except Exception:
        return None, r.text
    try:
        content = data['choices'][0]['message'].get('content', '')
    except Exception:
        content = None
    return content, data

def _do_request_with_payload(payload, max_attempts=2, timeout=8, slow_label='GigaChat'):
    token = _get_cached_token()
    if not token:
        return {'success': False, 'error': 'ИИ помощник не настроен', 'raw': None}
    attempt = 0
    last_err = None
    while attempt < max_attempts:
        attempt += 1
        try:
            start = time.time()
            r = _safe_post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=(3, timeout)
            )
            elapsed = time.time() - start
            if elapsed > 5:
                logger.warning('Slow %s request: %.2fs (attempt %s)', slow_label, elapsed, attempt)

            if r.status_code == 200:
                content, data = _extract_content_from_response(r)
                if content is None and data is None:
                    return {'success': False, 'error': 'Invalid JSON from API', 'raw': r.text}
                return {'success': True, 'raw': content, 'response': data}

            last_err = f'HTTP {r.status_code}'
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(attempt * 1.0)
                continue
            return {'success': False, 'error': f'Ошибка API GigaChat (код {r.status_code})', 'raw': r.text}
        except requests.exceptions.RequestException as exc:
            last_err = str(exc)
            logger.exception('RequestException on GigaChat request: %s', exc)
            time.sleep(attempt * 0.5)
            continue
    return {'success': False, 'error': f'Ошибка соединения с GigaChat: {last_err}', 'raw': None}

def post_to_gigachat(user_text: str, max_attempts: int = 2, timeout: int = 8):
    prompt = build_gigachat_prompt(user_text) if build_gigachat_prompt else ''
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.0,
        "max_tokens": 300
    }
    return _do_request_with_payload(payload, max_attempts=max_attempts, timeout=timeout, slow_label='GigaChat')

def post_conversation(user_text: str, max_attempts: int = 2, timeout: int = 8):
    system_prompt = (
        "Ты — дружелюбный и полезный ассистент. Отвечай на вопросы пользователя понятно и кратко."
        " Отвечай на русском языке. Никогда не добавляй служебный текст, просто ответ пользователя."
    )
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.0,
        "max_tokens": 300
    }
    return _do_request_with_payload(payload, max_attempts=max_attempts, timeout=timeout, slow_label='GigaChat-conv')

def post_custom(system_prompt: str, user_text: str, max_attempts: int = 2, timeout: int = 8):
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.0,
        "max_tokens": 300
    }
    return _do_request_with_payload(payload, max_attempts=max_attempts, timeout=timeout, slow_label='GigaChat-custom')
