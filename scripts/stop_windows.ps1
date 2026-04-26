<#
    FinAlly - stop and remove the container on Windows (PowerShell).
    The named volume 'finally-data' is intentionally NOT removed so SQLite
    data persists across restarts. Use `docker volume rm finally-data` to wipe it.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$Container = 'finally'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error 'docker is not installed or not on PATH.'
    exit 1
}

$existing = docker ps -a --format '{{.Names}}' | Where-Object { $_ -eq $Container }
if ($existing) {
    Write-Host "Stopping container '$Container'..."
    docker rm -f $Container | Out-Null
    Write-Host "Container removed. Volume 'finally-data' was preserved."
} else {
    Write-Host "No container named '$Container' is running."
}
