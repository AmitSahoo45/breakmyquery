"""Environment settings anchored to the repository, never the shell's cwd."""

from dataclasses import dataclass, field
from pathlib import Path
import math
import os
import tomllib
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = ROOT / '.streamlit' / 'secrets.toml'
GEMINI_MODELS = frozenset(('gemma-4-26b-a4b-it', 'gemma-4-31b-it'))


@dataclass(frozen=True)
class Settings:
    model: str = 'gemma4:e4b'
    ollama_host: str = 'http://localhost:11434'
    hunt_order: tuple[str, ...] = ('gemma', 'fuzz')
    gemma_rounds: int = 2
    fuzz_max: int = 400
    fuzz_seconds: float = 5.0
    query_timeout: float = 2.0
    data_dir: Path = ROOT / '.bmq'
    ollama_timeout: float = 45.0
    model_hints: bool = True
    model_provider: str = 'ollama'
    public_demo: bool = False
    gemini_api_key: str = field(default='', repr=False, compare=False)


def _gemini_key() -> str:
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if key:
        return key
    try:
        value = tomllib.loads(SECRETS_PATH.read_text(encoding='utf-8-sig')).get('GEMINI_API_KEY', '')
        return value.strip() if isinstance(value, str) else ''
    except (OSError, ValueError):
        # TOML exceptions can include a source line. Never surface secret text.
        return ''


def _boolean(name: str, default: str) -> bool:
    value = os.environ.get(name, default).strip().lower()
    if value not in ('true', 'false'):
        raise ValueError(f'{name} must be true or false.')
    return value == 'true'


def _number(name: str, default: int | float, *, integer: bool = False):
    value = int(os.environ.get(name, default)) if integer else float(os.environ.get(name, default))
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} must be a finite nonnegative number.')
    return value


def get_settings() -> Settings:
    provider = os.environ.get('BMQ_MODEL_PROVIDER', 'ollama').strip().lower()
    if provider not in ('ollama', 'gemini'):
        raise ValueError('BMQ_MODEL_PROVIDER must be ollama or gemini.')
    public_demo = _boolean('BMQ_PUBLIC_DEMO', 'false')
    model = os.environ.get('BMQ_MODEL', 'gemma-4-26b-a4b-it' if provider == 'gemini' else 'gemma4:e4b')
    if provider == 'gemini' and model not in GEMINI_MODELS:
        raise ValueError('BMQ_MODEL must name a supported hosted Gemma 4 model.')
    host = os.environ.get('BMQ_OLLAMA_HOST', 'http://localhost:11434')
    parsed = urlparse(host)
    if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('BMQ_OLLAMA_HOST must point to local Ollama on a loopback address.')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('BMQ_OLLAMA_HOST must be a local server URL without credentials or query parameters.')
    data_dir = Path(os.environ.get('BMQ_DATA_DIR', '.bmq'))
    data_dir = (ROOT / data_dir).resolve()
    if not data_dir.is_relative_to(ROOT):
        raise ValueError('BMQ_DATA_DIR must stay inside the repository.')
    order = tuple(part.strip() for part in os.environ.get('BMQ_HUNT_ORDER', 'gemma,fuzz').split(',') if part.strip())
    if not order or len(set(order)) != len(order) or any(part not in ('gemma', 'fuzz') for part in order):
        raise ValueError('BMQ_HUNT_ORDER must be gemma, fuzz, or each once separated by a comma.')
    hints = _boolean('BMQ_MODEL_HINTS', 'true')
    rounds = _number('BMQ_GEMMA_ROUNDS', 2, integer=True)
    settings = Settings(
        model=model,
        ollama_host=host,
        hunt_order=order,
        gemma_rounds=min(rounds, 1) if provider == 'gemini' else rounds,
        fuzz_max=_number('BMQ_FUZZ_MAX', 400, integer=True),
        fuzz_seconds=_number('BMQ_FUZZ_SECONDS', 5),
        query_timeout=_number('BMQ_QUERY_TIMEOUT', 2),
        data_dir=data_dir,
        ollama_timeout=_number('BMQ_OLLAMA_TIMEOUT', 45),
        model_hints=hints and provider == 'ollama' and not public_demo,
        model_provider=provider,
        public_demo=public_demo,
        gemini_api_key=_gemini_key() if provider == 'gemini' else '',
    )
    if settings.query_timeout == 0 or settings.ollama_timeout == 0:
        raise ValueError('Query and Ollama timeouts must be greater than zero.')
    return settings
