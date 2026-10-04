"""Environment settings anchored to the repository, never the shell's cwd."""

from dataclasses import dataclass
from pathlib import Path
import math
import os
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


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


def _number(name: str, default: int | float, *, integer: bool = False):
    value = int(os.environ.get(name, default)) if integer else float(os.environ.get(name, default))
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} must be a finite nonnegative number.')
    return value


def get_settings() -> Settings:
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
    hints = os.environ.get('BMQ_MODEL_HINTS', 'true').strip().lower()
    if hints not in ('true', 'false'):
        raise ValueError('BMQ_MODEL_HINTS must be true or false.')
    settings = Settings(
        model=os.environ.get('BMQ_MODEL', 'gemma4:e4b'),
        ollama_host=host,
        hunt_order=order,
        gemma_rounds=_number('BMQ_GEMMA_ROUNDS', 2, integer=True),
        fuzz_max=_number('BMQ_FUZZ_MAX', 400, integer=True),
        fuzz_seconds=_number('BMQ_FUZZ_SECONDS', 5),
        query_timeout=_number('BMQ_QUERY_TIMEOUT', 2),
        data_dir=data_dir,
        ollama_timeout=_number('BMQ_OLLAMA_TIMEOUT', 45),
        model_hints=hints == 'true',
    )
    if settings.query_timeout == 0 or settings.ollama_timeout == 0:
        raise ValueError('Query and Ollama timeouts must be greater than zero.')
    return settings
