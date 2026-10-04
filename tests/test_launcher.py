"""Exercise the Windows launcher without starting a server or model."""

import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='PowerShell launcher is Windows-only')


def launch(cwd, *arguments):
    environment = os.environ.copy()
    # Reproduce Windows' legacy console default; the launcher must override it.
    environment['PYTHONUTF8'] = '0'
    environment['PYTHONIOENCODING'] = 'cp1252'
    return subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
         str(ROOT / 'scripts/run.ps1'), *arguments],
        cwd=cwd, env=environment, capture_output=True, timeout=45,
    )


def test_launcher_uses_repo_root_and_utf8_for_streamlit_help(tmp_path):
    result = launch(tmp_path, '--help')
    assert result.returncode == 0, result.stderr.decode('utf-8', errors='replace')
    output = result.stdout.decode('utf-8', errors='replace')
    assert 'Usage: streamlit run' in output
    assert 'UnicodeEncodeError' not in output
    assert '\u2191' in output


def test_launcher_forwards_invalid_option_and_exit_status(tmp_path):
    result = launch(tmp_path, '--bmq-invalid-option')
    assert result.returncode == 2
    assert b'No such option' in result.stderr
    assert b'--bmq-invalid-option' in result.stderr
