param([string]$Output = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Output) { $Output = Join-Path $projectRoot ("backup-stock-chat-{0}.db" -f (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$container = docker compose -f (Join-Path $projectRoot 'compose.yaml') ps -q backend
if (-not $container) { throw 'Backend container is not running.' }
$temp = "/data/backup-$([Guid]::NewGuid().ToString('N')).db"
docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T backend python -c "import sqlite3; s=sqlite3.connect('/data/stock-chat.db'); d=sqlite3.connect('$temp'); s.backup(d); d.close(); s.close()"
docker cp "${container}:${temp}" $Output
docker compose -f (Join-Path $projectRoot 'compose.yaml') exec -T backend rm -f $temp
Write-Host "Backup written to $Output"
