param(
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) 'backups')
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'git was not found on PATH.'
}

$trackedFiles = git -C $repoRoot ls-files
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to enumerate tracked files.'
}

if (-not $trackedFiles) {
    Write-Host 'No tracked files found.'
    exit 0
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path $OutputDirectory $timestamp
$archivePath = Join-Path $OutputDirectory "tracked-files-$timestamp.zip"

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

foreach ($relativePath in $trackedFiles) {
    $sourcePath = Join-Path $repoRoot $relativePath
    $destinationPath = Join-Path $backupRoot $relativePath
    $destinationDirectory = Split-Path -Parent $destinationPath
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
}

if (Test-Path $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}

Compress-Archive -Path (Join-Path $backupRoot '*') -DestinationPath $archivePath -Force
Write-Host "Backup created at $archivePath"
