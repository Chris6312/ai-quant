#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$SkipFrontendInstall,
    [switch]$RunMigrations
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$BackendRoot = Join-Path $RepoRoot 'backend'
$FrontendRoot = Join-Path $RepoRoot 'frontend'
$ComposeFile = Join-Path $RepoRoot 'docker-compose.yml'
$BackendVenvPython = Join-Path $BackendRoot '.venv\Scripts\python.exe'

$NpmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $NpmCmd) {
    $NpmCmd = (Get-Command npm -ErrorAction SilentlyContinue).Source
}

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Throw-IfMissingPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port
    )

    $client = $null
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        $connected = $asyncResult.AsyncWaitHandle.WaitOne(1500, $false)

        if (-not $connected) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $client) {
            $client.Dispose()
        }
    }
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-Ok "$Name is accepting connections on $HostName`:$Port."
            return
        }
        Start-Sleep -Seconds 2
    }

    throw "$Name did not become ready on $HostName`:$Port in time."
}

function Get-EncodedPwshCommand {
    param([Parameter(Mandatory = $true)][string]$CommandText)

    $bytes = [System.Text.Encoding]::Unicode.GetBytes($CommandText)
    return [Convert]::ToBase64String($bytes)
}

Throw-IfMissingPath -Path $RepoRoot -Label 'Repo root'
Throw-IfMissingPath -Path $BackendRoot -Label 'Backend folder'
Throw-IfMissingPath -Path $FrontendRoot -Label 'Frontend folder'
Throw-IfMissingPath -Path $ComposeFile -Label 'docker-compose.yml'
Throw-IfMissingPath -Path $BackendVenvPython -Label 'Backend virtual environment python'

if (-not $NpmCmd) {
    throw 'npm was not found on PATH. Install Node.js and retry.'
}

if (-not (Get-Command wt.exe -ErrorAction SilentlyContinue)) {
    throw 'wt.exe was not found on PATH. Install Windows Terminal and retry.'
}

Write-Step 'Starting database and Redis containers'
Set-Location -LiteralPath $RepoRoot
docker compose -f $ComposeFile up -d db redis
if ($LASTEXITCODE -ne 0) {
    throw 'docker compose up -d db redis failed.'
}
Write-Ok 'db and redis containers were started.'

Write-Step 'Waiting for PostgreSQL and Redis readiness'
Wait-ForPort -Name 'PostgreSQL' -HostName '127.0.0.1' -Port 5432 -TimeoutSeconds 120
Wait-ForPort -Name 'Redis' -HostName '127.0.0.1' -Port 6379 -TimeoutSeconds 120

if ($RunMigrations) {
    Write-Step 'Running Alembic migrations'
    Push-Location $BackendRoot
    try {
        & $BackendVenvPython -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) {
            throw 'Alembic upgrade head failed.'
        }
        Write-Ok 'Alembic migrations completed.'
    }
    finally {
        Pop-Location
    }
}

if (-not $SkipFrontendInstall) {
    $NodeModulesPath = Join-Path $FrontendRoot 'node_modules'
    if (-not (Test-Path -LiteralPath $NodeModulesPath)) {
        Write-Step 'Installing frontend dependencies because node_modules was not found'
        Push-Location $FrontendRoot
        try {
            & $NpmCmd install
            if ($LASTEXITCODE -ne 0) {
                throw 'npm install failed.'
            }
            Write-Ok 'Frontend dependencies installed.'
        }
        finally {
            Pop-Location
        }
    }
    else {
        Write-Ok 'Frontend dependencies already present.'
    }
}

$CeleryDefaultCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$BackendRoot'
`$env:PYTHONPATH = '$BackendRoot'
Write-Host 'Starting Celery default worker...' -ForegroundColor Cyan
& '$BackendVenvPython' -m celery -A app.tasks.worker:celery_app worker -Q default --loglevel=INFO --pool=solo --hostname=default@%h
exit `$LASTEXITCODE
"@

$CeleryMlCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$BackendRoot'
`$env:PYTHONPATH = '$BackendRoot'
Write-Host 'Starting Celery ML worker...' -ForegroundColor Cyan
& '$BackendVenvPython' -m celery -A app.tasks.worker:celery_app worker -Q ml --loglevel=INFO --pool=solo --hostname=ml@%h
exit `$LASTEXITCODE
"@

$StartupMlSentimentCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$BackendRoot'
`$env:PYTHONPATH = '$BackendRoot'

Write-Host 'Waiting for Celery workers before startup ML, sentiment, and prediction sync...' -ForegroundColor Cyan
Start-Sleep -Seconds 15

Write-Host 'Dispatching startup ML daily candle sync...' -ForegroundColor Cyan
& '$BackendVenvPython' -m celery -A app.tasks.worker:celery_app call tasks.ml_candles.daily_sync --queue ml
if (`$LASTEXITCODE -ne 0) {
    throw 'Failed to dispatch startup ML daily candle sync.'
}

Write-Host 'Dispatching startup crypto news sentiment sync...' -ForegroundColor Cyan
& '$BackendVenvPython' -m celery -A app.tasks.worker:celery_app call tasks.news_sentiment.daily_crypto_sync --queue ml
if (`$LASTEXITCODE -ne 0) {
    throw 'Failed to dispatch startup crypto news sentiment sync.'
}

Write-Host 'Dispatching startup ML prediction refresh...' -ForegroundColor Cyan
& '$BackendVenvPython' -m celery -A app.tasks.worker:celery_app call tasks.ml_predictions.run --queue ml
if (`$LASTEXITCODE -ne 0) {
    throw 'Failed to dispatch startup ML prediction refresh.'
}

Write-Host 'Startup ML, sentiment, and prediction sync tasks dispatched.' -ForegroundColor Green
"@

$BackendCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$BackendRoot'
`$env:PYTHONPATH = '$BackendRoot'
Write-Host 'Starting FastAPI backend...' -ForegroundColor Cyan
& '$BackendVenvPython' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
exit `$LASTEXITCODE
"@

$FrontendCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$FrontendRoot'
Write-Host 'Starting Vite frontend...' -ForegroundColor Cyan
& '$NpmCmd' run dev -- --host 0.0.0.0
exit `$LASTEXITCODE
"@

$CeleryDefaultEncoded = Get-EncodedPwshCommand -CommandText $CeleryDefaultCommand
$CeleryMlEncoded = Get-EncodedPwshCommand -CommandText $CeleryMlCommand
$StartupMlSentimentEncoded = Get-EncodedPwshCommand -CommandText $StartupMlSentimentCommand
$BackendEncoded = Get-EncodedPwshCommand -CommandText $BackendCommand
$FrontendEncoded = Get-EncodedPwshCommand -CommandText $FrontendCommand

Write-Step 'Opening tabs in the current Windows Terminal window'

$wtArgs = @(
    '-w', '0',
    'new-tab',
    '--title', 'Celery Default',
    '--startingDirectory', $BackendRoot,
    'pwsh.exe', '-NoLogo', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $CeleryDefaultEncoded,
    ';',
    'new-tab',
    '--title', 'Celery ML',
    '--startingDirectory', $BackendRoot,
    'pwsh.exe', '-NoLogo', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $CeleryMlEncoded,
    ';',
    'new-tab',
    '--title', 'Startup ML + Sentiment',
    '--startingDirectory', $BackendRoot,
    'pwsh.exe', '-NoLogo', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $StartupMlSentimentEncoded,
    ';',
    'new-tab',
    '--title', 'Backend',
    '--startingDirectory', $BackendRoot,
    'pwsh.exe', '-NoLogo', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $BackendEncoded,
    ';',
    'new-tab',
    '--title', 'Frontend',
    '--startingDirectory', $FrontendRoot,
    'pwsh.exe', '-NoLogo', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $FrontendEncoded
)

& wt.exe @wtArgs

Write-Host ''
Write-Host 'Supervisor started.' -ForegroundColor Green
Write-Host 'Backend        : http://127.0.0.1:8000' -ForegroundColor White
Write-Host 'Frontend       : http://127.0.0.1:5173' -ForegroundColor White
Write-Host 'Celery default : queue default' -ForegroundColor White
Write-Host 'Celery ML      : queue ml' -ForegroundColor White