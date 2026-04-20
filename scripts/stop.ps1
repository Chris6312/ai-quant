$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$runRoot = Join-Path $repoRoot '.run'

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

Write-Host 'Shutdown complete.'
