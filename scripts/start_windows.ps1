<#
    FinAlly - start the container on Windows (PowerShell).

    Usage:
        scripts\start_windows.ps1
        scripts\start_windows.ps1 -Build       # force a rebuild
        scripts\start_windows.ps1 -OpenBrowser # also open the browser
#>

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'

$Image     = 'finally:latest'
$Container = 'finally'
$Volume    = 'finally-data'
$Port      = 8000

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker is not installed or not on PATH.'
    exit 1
}

$envArgs = @()
$envFile = Join-Path $RepoRoot '.env'
if (Test-Path $envFile) {
    $envArgs = @('--env-file', $envFile)
} else {
    Write-Warning "$envFile not found - copy .env.example to .env if you need API keys."
}

# Idempotent: remove any prior container with the same name.
$existing = docker ps -a --format '{{.Names}}' | Where-Object { $_ -eq $Container }
if ($existing) {
    Write-Host "Removing existing container '$Container'..."
    docker rm -f $Container | Out-Null
}

# Build the image if missing or -Build was passed.
$imagePresent = docker image inspect $Image 2>$null
if ($Build -or -not $imagePresent) {
    Write-Host "Building image '$Image'..."
    docker build -t $Image $RepoRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# Ensure the named volume exists.
$volumePresent = docker volume inspect $Volume 2>$null
if (-not $volumePresent) {
    docker volume create $Volume | Out-Null
}

Write-Host "Starting container '$Container' on port $Port..."
$runArgs = @(
    'run', '-d',
    '--name', $Container,
    '-p', "$Port`:8000",
    '-v', "$Volume`:/app/db"
) + $envArgs + @($Image)

docker @runArgs | Out-Null

$url = "http://localhost:$Port"
Write-Host "FinAlly is starting at $url"
Write-Host "  docker logs -f $Container     # follow logs"
Write-Host "  scripts\stop_windows.ps1      # stop"

if ($OpenBrowser) {
    Start-Process $url
}
