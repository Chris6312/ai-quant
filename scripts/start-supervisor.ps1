param(
    [switch]$NoFrontendInstall
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$backendRoot = Join-Path $repoRoot 'backend'
$frontendRoot = Join-Path $repoRoot 'frontend'
$runRoot = Join-Path $repoRoot '.run'

New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if ($null -eq $wt) {
    throw 'Windows Terminal (wt.exe) was not found on PATH.'
}

function New-SupervisorTab {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$PidFile,
        [Parameter(Mandatory = $true)][string[]]$CommandParts
    )

    $command = @"
& {
    `$ErrorActionPreference = 'Stop'
    Set-Location -LiteralPath '$WorkingDirectory'
    Set-Content -LiteralPath '$PidFile' -Value `$PID -Encoding ascii
    $($CommandParts -join ' ')
}
"@

    $arguments = @(
        'new-tab',
        '--title', $Title,
        'pwsh.exe',
        '-NoLogo',
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command', $command
    )

    Start-Process -FilePath 'wt.exe' -ArgumentList $arguments | Out-Null
}

if (-not $NoFrontendInstall) {
    if (-not (Test-Path (Join-Path $frontendRoot 'node_modules'))) {
        Write-Host 'Installing frontend dependencies...'
        Push-Location $frontendRoot
        try {
            npm install
        }
        finally {
            Pop-Location
        }
    }
}

New-SupervisorTab -Title 'Bot' -WorkingDirectory $backendRoot -PidFile (Join-Path $runRoot 'bot.pid') -CommandParts @(
    "Write-Host 'Starting Celery worker...';"
    "python -m celery -A app.tasks.worker worker --loglevel=INFO"
)

New-SupervisorTab -Title 'Backend' -WorkingDirectory $backendRoot -PidFile (Join-Path $runRoot 'backend.pid') -CommandParts @(
    "Write-Host 'Starting FastAPI backend...';"
    "uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
)

New-SupervisorTab -Title 'Frontend' -WorkingDirectory $frontendRoot -PidFile (Join-Path $runRoot 'frontend.pid') -CommandParts @(
    "Write-Host 'Starting React frontend...';"
    "npm run dev -- --host 0.0.0.0"
)

Write-Host "Supervisor started. PID files are in '$runRoot'."
Write-Host 'Use scripts/stop.ps1 to stop all processes.'
