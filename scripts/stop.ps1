#Requires -Version 5.1
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$RunRoot = Join-Path $RepoRoot '.run'
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

function Stop-ProcessFromPidFile {
    param(
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        Write-Warn "$Label PID file not found: $PidFile"
        return
    }

    $pidText = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($pidText)) {
        Write-Warn "$Label PID file was empty: $PidFile"
        Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
        return
    }

    $pid = 0
    if (-not [int]::TryParse($pidText.Trim(), [ref]$pid)) {
        Write-Warn "$Label PID file did not contain a valid PID: $PidFile"
        Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
        return
    }

    try {
        $process = Get-Process -Id $pid -ErrorAction Stop
        Write-Host "Requesting graceful shutdown for $Label (PID $pid, $($process.ProcessName))..." -ForegroundColor White

        $closed = $false
        try {
            $closed = $process.CloseMainWindow()
        }
        catch {
            $closed = $false
        }

        if ($closed) {
            Start-Sleep -Seconds 5
            $process.Refresh()
        }

        if (-not $process.HasExited) {
            Write-Warn "$Label did not exit gracefully; forcing stop for PID $pid."
            Stop-Process -Id $pid -Force -ErrorAction Stop
        }

        Write-Ok "$Label stopped."
    }
    catch {
        Write-Warn "$Label PID $pid is no longer running or could not be queried."
    }
    finally {
        Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
    }
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

$pidFiles = @(
    @{ Label = 'Celery';   Path = (Join-Path $RunRoot 'celery.pid') }
    @{ Label = 'Backend';  Path = (Join-Path $RunRoot 'backend.pid') }
    @{ Label = 'Frontend'; Path = (Join-Path $RunRoot 'frontend.pid') }
)

foreach ($entry in $pidFiles) {
    Stop-ProcessFromPidFile -PidFile $entry.Path -Label $entry.Label
}

Stop-DockerComposeServices

if (Test-Path -LiteralPath $RunRoot) {
    $remaining = Get-ChildItem -LiteralPath $RunRoot -Force -ErrorAction SilentlyContinue
    if ($null -eq $remaining -or $remaining.Count -eq 0) {
        Remove-Item -LiteralPath $RunRoot -Force -ErrorAction SilentlyContinue
        Write-Ok 'Removed empty .run directory.'
    }
    else {
        Write-Warn '.run directory still contains files; leaving it in place.'
    }
}

Write-Host "`nShutdown complete." -ForegroundColor Green