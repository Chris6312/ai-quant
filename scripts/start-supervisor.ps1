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
$RunRoot = Join-Path $RepoRoot '.run'

$BackendVenvPython = Join-Path $BackendRoot '.venv\Scripts\python.exe'
$NpmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not $NpmCmd) {
    $NpmCmd = (Get-Command npm -ErrorAction SilentlyContinue).Source
}

New-Item -ItemType Directory -Path $RunRoot -Force | Out-Null

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
        $client = New-Object System.Net.Sockets.TcpClient
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
        if ($client) {
            $client.Dispose()
        }
    }
}

function Wait-ForDocker {
    param([int]$TimeoutSeconds = 120)

    $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerCmd) {
        throw 'docker was not found on PATH.'
    }

    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok 'Docker is already running.'
        return
    }

    Write-Warn 'Docker is not ready. Attempting to start Docker Desktop...'

    $dockerDesktopCandidates = @(
        (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Docker\Docker\Docker Desktop.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    if ($dockerDesktopCandidates.Count -gt 0) {
        Start-Process -FilePath $dockerDesktopCandidates[0] | Out-Null
    }
    else {
        Write-Warn 'Docker Desktop executable was not found automatically. Start Docker Desktop manually if needed.'
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        docker info *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok 'Docker is ready.'
            return
        }
    }

    throw 'Docker did not become ready in time.'
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

function New-TabDefinition {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$CommandText
    )

    $encoded = Get-EncodedPwshCommand -CommandText $CommandText
    return "new-tab --title `"$Title`" --startingDirectory `"$WorkingDirectory`" pwsh.exe -NoLogo -NoExit -ExecutionPolicy Bypass -EncodedCommand $encoded"
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

Write-Step 'Checking Docker'
Wait-ForDocker

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

Write-Step 'Opening Windows Terminal tabs'

$CeleryPidFile = Join-Path $RunRoot 'celery.pid'
$BackendPidFile = Join-Path $RunRoot 'backend.pid'
$FrontendPidFile = Join-Path $RunRoot 'frontend.pid'

$CeleryCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$BackendRoot'
`$env:PYTHONPATH = '$BackendRoot'
Write-Host 'Starting Celery worker...' -ForegroundColor Cyan
`$child = Start-Process -FilePath '$BackendVenvPython' `
    -ArgumentList @('-m', 'celery', '-A', 'app.tasks.worker', 'worker', '--loglevel=INFO', '--pool=solo') `
    -WorkingDirectory '$BackendRoot' `
    -NoNewWindow `
    -PassThru
Set-Content -LiteralPath '$CeleryPidFile' -Value `$child.Id -Encoding ascii
Write-Host ('Celery PID: ' + `$child.Id) -ForegroundColor DarkGray
`$null = `$child.WaitForExit()
Remove-Item -LiteralPath '$CeleryPidFile' -ErrorAction SilentlyContinue
exit `$child.ExitCode
"@

$BackendCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$BackendRoot'
`$env:PYTHONPATH = '$BackendRoot'
Write-Host 'Starting FastAPI backend...' -ForegroundColor Cyan
`$child = Start-Process -FilePath '$BackendVenvPython' `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000') `
    -WorkingDirectory '$BackendRoot' `
    -NoNewWindow `
    -PassThru
Set-Content -LiteralPath '$BackendPidFile' -Value `$child.Id -Encoding ascii
Write-Host ('Backend PID: ' + `$child.Id) -ForegroundColor DarkGray
`$null = `$child.WaitForExit()
Remove-Item -LiteralPath '$BackendPidFile' -ErrorAction SilentlyContinue
exit `$child.ExitCode
"@

$FrontendCommand = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath '$FrontendRoot'
Write-Host 'Starting Vite frontend...' -ForegroundColor Cyan
`$child = Start-Process -FilePath '$NpmCmd' `
    -ArgumentList @('run', 'dev', '--', '--host', '0.0.0.0') `
    -WorkingDirectory '$FrontendRoot' `
    -NoNewWindow `
    -PassThru
Set-Content -LiteralPath '$FrontendPidFile' -Value `$child.Id -Encoding ascii
Write-Host ('Frontend PID: ' + `$child.Id) -ForegroundColor DarkGray
`$null = `$child.WaitForExit()
Remove-Item -LiteralPath '$FrontendPidFile' -ErrorAction SilentlyContinue
exit `$child.ExitCode
"@

$TabDefinitions = @(
    (New-TabDefinition -Title 'Celery'   -WorkingDirectory $BackendRoot  -CommandText $CeleryCommand)
    (New-TabDefinition -Title 'Backend'  -WorkingDirectory $BackendRoot  -CommandText $BackendCommand)
    (New-TabDefinition -Title 'Frontend' -WorkingDirectory $FrontendRoot -CommandText $FrontendCommand)
)

Start-Process -FilePath 'wt.exe' -ArgumentList ($TabDefinitions -join ' ; ') | Out-Null

Write-Host ''
Write-Host 'Supervisor started.' -ForegroundColor Green
Write-Host "Backend  : http://127.0.0.1:8000" -ForegroundColor White
Write-Host "Frontend : http://127.0.0.1:5173" -ForegroundColor White
Write-Host "Run dir  : $RunRoot" -ForegroundColor DarkGray
Write-Host ''
Write-Host 'Examples:' -ForegroundColor Cyan
Write-Host '  .\scripts\start-supervisor.ps1' -ForegroundColor White
Write-Host '  .\scripts\start-supervisor.ps1 -RunMigrations' -ForegroundColor White
Write-Host '  .\scripts\start-supervisor.ps1 -SkipFrontendInstall' -ForegroundColor White