$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([System.IO.Path]::GetPathRoot($repoRoot) -ne 'D:\') {
    throw 'Keep this project on D: before running setup.'
}
Set-Location -LiteralPath $repoRoot
New-Item -ItemType Directory -Force -Path '.cache\tmp', '.cache\pip' | Out-Null
$env:TEMP = Join-Path $repoRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $repoRoot '.cache\pip'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw 'A compatible Python was not found.' }
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& '.\.venv\Scripts\python.exe' -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11 or newer is required'"
if ($LASTEXITCODE -ne 0) { throw 'The virtual environment needs Python 3.11 or newer.' }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& '.\.venv\Scripts\python.exe' -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
