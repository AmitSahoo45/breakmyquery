"""Keep test-library temporary files inside this checkout before imports."""

import os
from pathlib import Path
import tempfile


_scratch = Path(__file__).resolve().parents[1] / '.cache' / 'tmp'
_scratch.mkdir(parents=True, exist_ok=True)
os.environ['TEMP'] = os.environ['TMP'] = str(_scratch)
# Pytest/plugins may have asked for gettempdir() before this conftest loaded.
tempfile.tempdir = str(_scratch)


import pytest


@pytest.fixture(autouse=True)
def isolate_hosted_credentials(monkeypatch):
    """Offline tests must never read the owner's key or call their project."""
    from bmq import config
    monkeypatch.setattr(config, 'SECRETS_PATH', _scratch / 'nonexistent-test-secrets.toml')
    for name in ('GEMINI_API_KEY', 'BMQ_MODEL_PROVIDER', 'BMQ_PUBLIC_DEMO'):
        monkeypatch.delenv(name, raising=False)
    from bmq import gemini
    def no_live_api(**kwargs):
        raise AssertionError('Offline tests must mock the Gemini HTTP transport.')
    monkeypatch.setattr(gemini, '_http_client', no_live_api)

