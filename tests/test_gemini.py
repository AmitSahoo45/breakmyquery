"""Hosted calls use one project, bounded requests, and local validation."""

import json
from dataclasses import replace

import httpx
import pytest

from bmq import config, llm
from bmq.config import Settings


def test_hosted_settings_are_explicit_and_hide_the_secret(monkeypatch):
    monkeypatch.setenv('BMQ_MODEL_PROVIDER', 'gemini')
    monkeypatch.setenv('BMQ_PUBLIC_DEMO', 'true')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret-not-real')
    settings = config.get_settings()
    assert settings.model == 'gemma-4-26b-a4b-it'
    assert settings.model_provider == 'gemini'
    assert settings.public_demo and not settings.model_hints
    assert settings.gemma_rounds == 1
    assert settings.gemini_api_key == 'test-secret-not-real'
    assert 'test-secret-not-real' not in repr(settings)


def test_repo_secret_loading_is_only_for_hosted_mode(monkeypatch, tmp_path):
    secret = tmp_path / 'secrets.toml'
    secret.write_text('GEMINI_API_KEY = "dummy-file-key"', encoding='utf-8')
    monkeypatch.setattr(config, 'SECRETS_PATH', secret)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    assert config.get_settings().gemini_api_key == ''
    monkeypatch.setenv('BMQ_MODEL_PROVIDER', 'gemini')
    assert config.get_settings().gemini_api_key == 'dummy-file-key'
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-env-key')
    assert config.get_settings().gemini_api_key == 'dummy-env-key'


@pytest.mark.parametrize('name,value', [
    ('BMQ_MODEL_PROVIDER', 'unknown'), ('BMQ_PUBLIC_DEMO', 'typo'),
])
def test_invalid_hosted_settings_fail_safely(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        config.get_settings()


@pytest.fixture
def hosted(monkeypatch):
    from bmq import gemini
    from bmq.quota import QuotaLimiter
    monkeypatch.setattr(gemini, 'LIMITER', QuotaLimiter())
    gemini.reset_note()
    return Settings(model_provider='gemini', model='gemma-4-26b-a4b-it',
                    gemini_api_key='dummy-private-key', public_demo=True)


def wire(monkeypatch, handler):
    from bmq import gemini
    original = httpx.Client
    def factory(**kwargs):
        assert kwargs['follow_redirects'] is False
        assert kwargs['trust_env'] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(gemini, '_http_client', factory)


def response(content='{"candidates": []}', *, finish='STOP'):
    return httpx.Response(200, json={'candidates': [{
        'finishReason': finish,
        'content': {'parts': [{'text': 'private thinking', 'thought': True}, {'text': content}]},
    }]})


def propose(settings):
    return llm.propose_datasets('CREATE TABLE customers (id INTEGER);', 'Question',
                               'SELECT 1', 'SELECT 2', [], settings=settings)


def test_one_bounded_request_has_header_secret_and_validated_output(monkeypatch, hosted):
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert 'dummy-private-key' not in str(request.url)
        assert request.headers['x-goog-api-key'] == 'dummy-private-key'
        body = json.loads(request.content)
        assert body['generationConfig']['maxOutputTokens'] <= 3072
        assert 'candidates' in body['systemInstruction']['parts'][0]['text']
        return response('{"candidates":[{"idea":"Empty parent", "inserts":[]}]}')
    wire(monkeypatch, handler)
    assert llm.model_available(hosted) is True
    assert seen == []  # status never spends quota
    assert propose(hosted)[0].idea == 'Empty parent'
    assert len(seen) == 1


@pytest.mark.parametrize('content,finish', [
    ('not json', 'STOP'), ('{"candidates": "wrong-type"}', 'STOP'),
    ('{"candidates": []}', 'MAX_TOKENS'),
])
def test_invalid_generation_does_not_trigger_repair(monkeypatch, hosted, content, finish):
    from bmq import gemini
    calls = []
    wire(monkeypatch, lambda request: calls.append(request) or response(content, finish=finish))
    assert propose(hosted) == []
    assert len(calls) == 1
    assert gemini.model_note()
    assert 'dummy-private-key' not in gemini.model_note()


@pytest.mark.parametrize('status', [301, 401, 403, 429, 500, 503])
def test_api_errors_fall_back_without_raw_error_text(monkeypatch, hosted, status):
    from bmq import gemini
    calls = []
    wire(monkeypatch, lambda request: calls.append(request) or httpx.Response(
        status, headers={'Retry-After': '30', 'Location': 'https://unrelated.example'},
        text='dummy-private-key SELECT private_error'))
    assert propose(hosted) == []
    assert len(calls) == 1
    assert gemini.model_note()
    assert 'private' not in gemini.model_note()
    if status == 429:
        assert propose(hosted) == []
        assert len(calls) == 1  # shared cooldown, no immediate retry


def test_oversized_input_and_missing_key_make_no_http_call(monkeypatch, hosted):
    wire(monkeypatch, lambda request: pytest.fail('must not send oversized or unconfigured request'))
    assert propose(replace(hosted, gemini_api_key='')) == []
    assert llm.propose_datasets('x' * 13000, 'Q', 'SELECT 1', 'SELECT 2', [], settings=hosted) == []


def test_model_allowlist_is_checked_before_url_construction(monkeypatch, hosted):
    wire(monkeypatch, lambda request: pytest.fail('unsupported model must not make HTTP calls'))
    assert propose(replace(hosted, model='../../other?key=secret')) == []


def test_timeout_and_oversized_response_release_the_slot(monkeypatch, hosted):
    from bmq import gemini
    def timeout(request):
        raise httpx.ReadTimeout('dummy-private-key', request=request)
    wire(monkeypatch, timeout)
    assert propose(hosted) == []
    assert gemini.LIMITER.acquire(1) is None
    gemini.LIMITER.release()
    wire(monkeypatch, lambda request: httpx.Response(200, content=b'x' * 256001))
    assert propose(hosted) == []
    assert gemini.model_note()


def test_hosted_explanations_never_spend_quota(monkeypatch, hosted):
    wire(monkeypatch, lambda request: pytest.fail('hosted teaching is disabled'))
    assert llm.explain_error('schema', 'SELECT 1', 'error', settings=hosted) is None


def test_context_notes_are_isolated():
    from contextvars import copy_context
    from bmq import gemini
    gemini.reset_note()
    other = copy_context()
    other.run(gemini.set_note, 'Busy.')
    assert gemini.model_note() is None
    assert other.run(gemini.model_note) == 'Busy.'


def test_single_json_code_fence_is_validated_without_another_call(monkeypatch, hosted):
    calls = []
    wire(monkeypatch, lambda request: calls.append(request) or response(
        '```json\n{"candidates":[{"idea":"No orders", "inserts":[]}]}\n```'))
    assert propose(hosted)[0].idea == 'No orders'
    assert len(calls) == 1


def test_fenced_json_with_extra_prose_is_not_accepted(monkeypatch, hosted):
    wire(monkeypatch, lambda request: response('A preface.\n```json\n{"candidates": []}\n```'))
    assert propose(hosted) == []
