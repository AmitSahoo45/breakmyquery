"""Single-project Gemma REST adapter; no retries, key rotation, or raw error logs."""

from contextvars import ContextVar
import json
import math
import re

import httpx

from bmq.config import GEMINI_MODELS, Settings
from bmq.quota import QuotaLimiter

MAX_RESPONSE_BYTES = 256_000
LIMITER = QuotaLimiter()
_note: ContextVar[str | None] = ContextVar('gemini_model_note', default=None)
_http_client = httpx.Client


def reset_note():
    _note.set(None)


def set_note(value: str):
    _note.set(value)


def model_note() -> str | None:
    return _note.get()


def configured(settings: Settings) -> bool:
    """Configuration presence, not a network health or model-quality claim."""
    return bool(settings.gemini_api_key.strip()) and settings.model in GEMINI_MODELS


def _retry_after(response) -> float:
    try:
        value = float(response.headers.get('Retry-After', '60'))
        return min(3600, max(1, value)) if math.isfinite(value) else 60
    except (TypeError, ValueError):
        return 60


def generate(schema, messages, temperature, settings):
    """Return a Pydantic-validated proposal or None, with a fixed safe notice."""
    if not configured(settings):
        set_note('Gemma API is not configured. Local stress tests remain available.')
        return None
    system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
    system += '\nReturn only JSON matching this schema:\n' + json.dumps(schema.model_json_schema())
    contents = [{'role': 'user' if m['role'] == 'user' else 'model',
                 'parts': [{'text': m['content']}]} for m in messages if m['role'] != 'system']
    payload = {
        'systemInstruction': {'parts': [{'text': system}]},
        'contents': contents,
        'generationConfig': {'temperature': temperature, 'maxOutputTokens': 3072,
                             'thinkingConfig': {'thinkingLevel': 'minimal'}},
    }
    # Reserve one token per UTF-8 byte plus protocol overhead. This deliberately
    # overestimates typical SQL prompts; it is not Google's tokenizer or quota.
    estimate = len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) + 256
    reason = LIMITER.acquire(estimate)
    if reason:
        set_note('Gemma request is too large. Local stress tests were used.' if reason == 'request_too_large'
                 else 'Gemma is busy or its demo allowance is resting. Local stress tests remain available; try again later.')
        return None
    try:
        timeout = min(settings.ollama_timeout, 45.0)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('Invalid timeout')
        with _http_client(timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
                          trust_env=False, follow_redirects=False) as client:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{settings.model}:generateContent'
            with client.stream('POST', url, headers={'x-goog-api-key': settings.gemini_api_key},
                               json=payload) as response:
                if response.status_code == 429:
                    LIMITER.cool_down(_retry_after(response))
                    set_note('Gemma reached its API allowance. Local stress tests remain available; try again later.')
                    return None
                if response.status_code != 200:
                    set_note('Gemma API is unavailable. Local stress tests remain available.')
                    return None
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=8192):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError('Response too large')
        result = json.loads(body)
        candidates = result.get('candidates', [])
        candidate = candidates[0] if candidates else {}
        if candidate.get('finishReason') != 'STOP':
            raise ValueError('Incomplete generation')
        content = ''.join(part.get('text', '') for part in candidate.get('content', {}).get('parts', [])
                          if not part.get('thought'))
        # Gemma may wrap its whole answer despite the JSON-only instruction.
        # Accept exactly one wrapper, never extract JSON out of extra prose.
        fenced = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', content, re.DOTALL)
        if fenced:
            content = fenced[1]
        parsed = schema.model_validate_json(content)
        reset_note()
        return parsed
    except (httpx.HTTPError, OSError):
        set_note('Gemma API could not be reached. Local stress tests remain available.')
        return None
    except (ValueError, TypeError, AttributeError, KeyError, IndexError):
        set_note('Gemma returned no usable dataset. Local stress tests remain available.')
        return None
    finally:
        LIMITER.release()
