"""Keep test-library temporary files inside this checkout before imports."""

import os
from pathlib import Path
import tempfile


_scratch = Path(__file__).resolve().parents[1] / '.cache' / 'tmp'
_scratch.mkdir(parents=True, exist_ok=True)
os.environ['TEMP'] = os.environ['TMP'] = str(_scratch)
# Pytest/plugins may have asked for gettempdir() before this conftest loaded.
tempfile.tempdir = str(_scratch)

