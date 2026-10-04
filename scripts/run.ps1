param([switch]$PublicDemo)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([System.IO.Path]::GetPathRoot($repoRoot) -ne 'D:\') {
    throw 'Keep this project on D: before running it.'
}
Set-Location -LiteralPath $repoRoot

# Set paths before Python imports Streamlit or creates temporary files.
New-Item -ItemType Directory -Force -Path '.cache\tmp', '.cache\pip', '.cache\profile', '.cache\appdata', '.cache\localappdata', '.cache\ollama\models' | Out-Null
$env:TEMP = Join-Path $repoRoot '.cache\tmp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $repoRoot '.cache\pip'
$env:USERPROFILE = Join-Path $repoRoot '.cache\profile'
$env:APPDATA = Join-Path $repoRoot '.cache\appdata'
$env:LOCALAPPDATA = Join-Path $repoRoot '.cache\localappdata'
$env:OLLAMA_MODELS = Join-Path $repoRoot '.cache\ollama\models'
$env:PYTHONPYCACHEPREFIX = Join-Path $repoRoot '.cache\pycache'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'
$env:STREAMLIT_SERVER_ADDRESS = '127.0.0.1'
if (-not $env:BMQ_DATA_DIR) { $env:BMQ_DATA_DIR = '.bmq' }

$pythonExe = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Local Python is missing. Run scripts\setup.ps1 first.'
}
$appEntry = if ($PublicDemo) { 'cloud_app.py' } else { 'app.py' }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $appEntry))) {
    throw "$appEntry is missing from the repository."
}
& $pythonExe -m streamlit run $appEntry @args
exit $LASTEXITCODE
