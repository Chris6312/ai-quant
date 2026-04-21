#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'SilentlyContinue'

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$ComposeFile = Join-Path $RepoRoot 'docker-compose.yml'

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "    OK: $Message" -ForegroundColor Green
}

function Write-Warn {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "    WARN: $Message" -ForegroundColor Yellow
}

function Stop-ProcessTreeByPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )

    $targets = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match $Pattern -and
        $_.Name -notmatch 'pwsh|powershell'
    }

    if (-not $targets) {
        Write-Warn "$DisplayName is not running."
        return
    }

    $targets = $targets | Sort-Object ProcessId -Unique

    foreach ($proc in $targets) {
        Write-Host "Stopping $DisplayName (PID $($proc.ProcessId))..." -ForegroundColor White
        & taskkill.exe /PID $proc.ProcessId /T /F | Out-Null
    }

    Write-Ok "$DisplayName stopped."
}

function Stop-DockerComposeServices {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Warn 'Docker was not found on PATH; skipping Docker Compose shutdown.'
        return
    }

    if (-not (Test-Path -LiteralPath $ComposeFile)) {
        Write-Warn 'docker-compose.yml was not found; skipping Docker Compose shutdown.'
        return
    }

    Write-Step 'Stopping Docker Compose services (db, redis)'
    & docker compose -f $ComposeFile stop db redis
    if ($LASTEXITCODE -ne 0) {
        Write-Warn 'Docker Compose stop returned a non-zero exit code.'
        return
    }

    Write-Ok 'db and redis containers were stopped.'
}

Write-Step 'Stopping app processes'

# Frontend first
Stop-ProcessTreeByPattern -Pattern 'vite|npm(\.cmd)? run dev' -DisplayName 'Frontend'

# Backend next
Stop-ProcessTreeByPattern -Pattern 'uvicorn.*app\.main:app|app\.main:app.*--reload' -DisplayName 'Backend'

# Celery last
Stop-ProcessTreeByPattern -Pattern 'celery.*app\.tasks\.worker|app\.tasks\.worker.*celery' -DisplayName 'Celery'

Start-Sleep -Seconds 2
Stop-DockerComposeServices

Write-Host "`nShutdown complete." -ForegroundColor Green