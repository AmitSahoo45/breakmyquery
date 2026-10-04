param([switch]$Stop, [switch]$Status, [switch]$Warmup)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([System.IO.Path]::GetPathRoot($repoRoot) -ne 'D:\') { throw 'Keep this project on D:.' }
if ($Stop -and $Status) { throw 'Choose either -Stop or -Status.' }
if ($Warmup -and ($Stop -or $Status)) { throw '-Warmup cannot be combined with -Stop or -Status.' }
$dockerExe = (Get-Command docker.exe -ErrorAction Stop).Source
$dockerHost = 'npipe:////./pipe/dockerDesktopLinuxEngine'
$containerName = 'breakmyquery-llama32'
$imageId = 'sha256:e0ae5354a9e4c85160df4698a45ae360cd0c12ef90e484b12fc870c28f491892'
$modelName = 'llama3.2:latest'
$runtimeRoot = Join-Path $repoRoot '.cache\ollama\runtime'
$modelsRoot = Join-Path $repoRoot '.cache\ollama\models'
$configRoot = Join-Path $repoRoot '.cache\ollama\docker-config'
$dockerOptions = @('--config', $configRoot, '--host', $dockerHost)

# Apply isolation before even read-only Docker commands or initial model copies.
$savedEnvironment = @{}
$redirects = @{ TEMP=(Join-Path $runtimeRoot 'tmp'); TMP=(Join-Path $runtimeRoot 'tmp');
    USERPROFILE=(Join-Path $runtimeRoot 'profile'); APPDATA=(Join-Path $runtimeRoot 'appdata');
    LOCALAPPDATA=(Join-Path $runtimeRoot 'localappdata') }
New-Item -ItemType Directory -Force -Path $runtimeRoot, $modelsRoot, $configRoot,
    (Join-Path $runtimeRoot 'tmp'), (Join-Path $runtimeRoot 'profile'), (Join-Path $runtimeRoot 'cache'),
    (Join-Path $runtimeRoot 'appdata'), (Join-Path $runtimeRoot 'localappdata') | Out-Null
try {
foreach ($key in $redirects.Keys) {
    $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
    [Environment]::SetEnvironmentVariable($key, $redirects[$key], 'Process')
}

function Invoke-Docker {
    param([string[]]$Arguments)
    $output = & $dockerExe @dockerOptions @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $output" }
    return ($output -join "`n")
}

function Get-OwnedContainer {
    $names = Invoke-Docker -Arguments @('ps', '-a', '--format', '{{.Names}}')
    if ($containerName -notin ($names -split "`n")) { return $null }
    $details = (Invoke-Docker -Arguments @('inspect', $containerName) | ConvertFrom-Json)[0]
    if ($details.Config.Labels.'breakmyquery.repo' -ne $repoRoot -or $details.Image -ne $imageId) {
        throw 'The dedicated container name belongs to another runtime; refusing to change it.'
    }
    if (-not $details.HostConfig.ReadonlyRootfs -or $details.HostConfig.LogConfig.Type -ne 'none') {
        throw 'The dedicated container lacks the required read-only filesystem/log isolation.'
    }
    $ports = @($details.HostConfig.PortBindings.PSObject.Properties)
    if ($ports.Count -ne 1 -or $ports[0].Name -ne '11434/tcp' -or @($ports[0].Value).Count -ne 1) {
        throw 'The dedicated container must publish exactly one loopback port binding.'
    }
    $binding = $ports[0].Value[0]
    if ($binding.HostIp -ne '127.0.0.1' -or $binding.HostPort -ne '11435') {
        throw 'The dedicated container has unexpected port bindings.'
    }
    $expectedMounts = @{ '/models'=$modelsRoot; '/runtime'=$runtimeRoot;
        '/tmp'=(Join-Path $runtimeRoot 'tmp'); '/root'=(Join-Path $runtimeRoot 'profile') }
    if (@($details.Mounts).Count -ne $expectedMounts.Count) { throw 'Unexpected dedicated container mounts.' }
    foreach ($mount in $details.Mounts) {
        if ($mount.Type -ne 'bind' -or $mount.Source -ne $expectedMounts[$mount.Destination]) {
            throw 'Dedicated container writes are not bound to the expected repository paths.'
        }
    }
    return $details
}

function Get-Health {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/version' -TimeoutSec 3
    $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/tags' -TimeoutSec 3
    if ($modelName -notin @($tags.models.name)) { throw 'The selected Llama model is missing.' }
    [PSCustomObject]@{ endpoint = 'http://127.0.0.1:11435'; model = $modelName; version = $health.version; container = $containerName }
}

function Invoke-Warmup {
    $request = @{ model=$modelName; prompt=''; stream=$false; keep_alive='30m'; options=@{num_ctx=8192} } | ConvertTo-Json -Compress
    $response = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/generate' -Method Post `
        -ContentType 'application/json' -Body $request -TimeoutSec 240
    if (-not $response.done) { throw 'Model warmup did not finish successfully.' }
}

$existing = Get-OwnedContainer
if ($Stop) {
    if ($existing -and $existing.State.Running) {
        Invoke-Docker -Arguments @('stop', '--time', '10', $containerName) | Out-Null
    }
    Write-Output 'Dedicated BreakMyQuery runtime stopped; owner localhost11434 service was not changed.'
    exit 0
}
if ($existing -and $existing.State.Running) {
    $ready = Get-Health
    if ($Warmup) { Invoke-Warmup; $ready | Add-Member -NotePropertyName warmed -NotePropertyValue $true }
    $ready | ConvertTo-Json -Compress
    exit 0
}
if ($Status) { throw 'Dedicated BreakMyQuery runtime is not running.' }

# Check before any start/copy. Never adopt a service belonging to another process.
$portProbe = New-Object System.Net.Sockets.TcpClient
try {
    $connected = $portProbe.ConnectAsync('127.0.0.1', 11435)
    if ($connected.Wait(1000) -and $portProbe.Connected) { throw 'Port 11435 is occupied by an unrelated service.' }
} catch [System.AggregateException] {
    # A refused connection means the loopback port is available.
} finally { $portProbe.Dispose() }

# Never pull an image/model. Reuse the immutable, already-installed Linux image.
Invoke-Docker -Arguments @('image', 'inspect', $imageId) | Out-Null
$manifestRelative = 'manifests/registry.ollama.ai/library/llama3.2/latest'
$sourceManifest = '/root/.ollama/models/' + $manifestRelative
$manifestDirectory = Join-Path $modelsRoot 'manifests\registry.ollama.ai\library\llama3.2'
$manifestPath = Join-Path $manifestDirectory 'latest'
New-Item -ItemType Directory -Force -Path $manifestDirectory, (Join-Path $modelsRoot 'blobs') | Out-Null
$manifest = Invoke-Docker -Arguments @('exec', 'rag-ollama', 'cat', $sourceManifest)
$parsed = $manifest | ConvertFrom-Json
$digests = @($parsed.config.digest) + @($parsed.layers.digest)
foreach ($digest in $digests) {
    if ($digest -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid blob digest in existing model manifest.' }
    $blobName = $digest.Replace(':', '-')
    $destination = Join-Path $modelsRoot ('blobs\' + $blobName)
    if (-not (Test-Path -LiteralPath $destination)) {
        $partial = $destination + '.partial'
        Invoke-Docker -Arguments @('cp', ('rag-ollama:/root/.ollama/models/blobs/' + $blobName), $partial) | Out-Null
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest.Substring(7)) {
            Remove-Item -LiteralPath $partial
            throw 'Copied model blob failed its SHA-256 integrity check.'
        }
        Move-Item -LiteralPath $partial -Destination $destination
    }
}
# Copy exact manifest bytes, preserving its content digest and the owner's source.
Invoke-Docker -Arguments @('cp', ('rag-ollama:' + $sourceManifest), $manifestPath) | Out-Null

if ($existing) { Invoke-Docker -Arguments @('rm', $containerName) | Out-Null }
$runArguments = @('run', '--pull=never', '--name', $containerName, '--read-only', '--log-driver', 'none',
    '--label', ('breakmyquery.repo=' + $repoRoot), '--gpus', 'all',
    '--publish', '127.0.0.1:11435:11434',
    '--mount', ('type=bind,source=' + $modelsRoot + ',target=/models'),
    '--mount', ('type=bind,source=' + $runtimeRoot + ',target=/runtime'),
    '--mount', ('type=bind,source=' + (Join-Path $runtimeRoot 'tmp') + ',target=/tmp'),
    '--mount', ('type=bind,source=' + (Join-Path $runtimeRoot 'profile') + ',target=/root'),
    '--env', 'HOME=/runtime/profile', '--env', 'TMPDIR=/runtime/tmp',
    '--env', 'XDG_CACHE_HOME=/runtime/cache', '--env', 'OLLAMA_MODELS=/models',
    '--env', 'OLLAMA_HOST=0.0.0.0:11434', '--env', 'OLLAMA_NO_CLOUD=true', $imageId, 'serve')
# Start-Process joins arguments; quote each value to retain Windows paths with spaces.
$quotedArguments = @($dockerOptions + $runArguments | ForEach-Object { '"' + $_ + '"' })
$startOptions = @{ FilePath=$dockerExe; ArgumentList=$quotedArguments; WindowStyle='Hidden'; PassThru=$true;
    WorkingDirectory=$repoRoot; RedirectStandardOutput=(Join-Path $runtimeRoot 'stdout.log');
    RedirectStandardError=(Join-Path $runtimeRoot 'stderr.log') }
$process = Start-Process @startOptions
[System.IO.File]::WriteAllText((Join-Path $runtimeRoot 'client.pid'), [string]$process.Id)
$deadline = [DateTime]::UtcNow.AddSeconds(30)
do {
    try { $ready = Get-Health; break } catch {
        $process.Refresh()
        if ($process.HasExited) { throw "Dedicated runtime exited. Read $runtimeRoot\stderr.log." }
        Start-Sleep -Milliseconds 250
    }
} while ([DateTime]::UtcNow -lt $deadline)
if (-not $ready) { throw "Dedicated runtime did not become healthy. Read $runtimeRoot\stderr.log." }
Get-OwnedContainer | Out-Null
if ($Warmup) { Invoke-Warmup; $ready | Add-Member -NotePropertyName warmed -NotePropertyValue $true }
$ready | Add-Member -NotePropertyName client_pid -NotePropertyValue $process.Id
$ready | ConvertTo-Json -Compress
} finally {
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process') }
}
