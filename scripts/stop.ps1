$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$runRoot = Join-Path $repoRoot '.run'
$composeFile = Join-Path $repoRoot 'docker-compose.yml'

function Stop-DockerComposeServices {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host 'Docker was not found on PATH; skipping Docker Compose shutdown.'
        return
    }

    if (-not (Test-Path $composeFile)) {
        Write-Host 'docker-compose.yml was not found; skipping Docker Compose shutdown.'
        return
    }

    Write-Host 'Stopping Docker Compose services (db, redis)...'
    & docker compose -f $composeFile stop db redis
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Docker Compose stop returned a non-zero exit code.'
    }
}

$pidFiles = @(
    Join-Path $runRoot 'bot.pid',
    Join-Path $runRoot 'backend.pid',
    Join-Path $runRoot 'frontend.pid'
)

foreach ($pidFile in $pidFiles) {
    if (-not (Test-Path $pidFile)) {
        continue
    }

    $pidText = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($pidText)) {
        continue
    }

    $pid = [int]$pidText
    try {
        $process = Get-Process -Id $pid -ErrorAction Stop
        Write-Host "Requesting graceful shutdown for PID $pid ($($process.ProcessName))..."
        [void]$process.CloseMainWindow()
        Start-Sleep -Seconds 5
        if (-not $process.HasExited) {
            Write-Host "Forcing shutdown for PID $pid..."
            Stop-Process -Id $pid -Force
        }
    }
    catch {
        Write-Host "PID $pid is no longer running or could not be stopped gracefully."
    }
    finally {
        Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    }
}

if (Test-Path $runRoot) {
    $remaining = Get-ChildItem -LiteralPath $runRoot -File -ErrorAction SilentlyContinue
    if ($null -eq $remaining -or $remaining.Count -eq 0) {
        Remove-Item -LiteralPath $runRoot -Force -ErrorAction SilentlyContinue
    }
}

Stop-DockerComposeServices

Write-Host 'Shutdown complete.'
