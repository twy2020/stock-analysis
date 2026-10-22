param(
  [Parameter(Mandatory = $true)]
  [string]$Backup
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $projectRoot 'compose.yaml'
$dataVolume = 'stock-analysis-chat-data'

if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) {
  throw "Backup file not found: $Backup"
}
$backupPath = (Resolve-Path -LiteralPath $Backup).Path

docker volume inspect $dataVolume *> $null
if ($LASTEXITCODE -ne 0) { throw "Data volume not found: $dataVolume" }

docker compose -f $composeFile stop backend
try {
  docker compose -f $composeFile run --rm --no-deps `
    --volume "${backupPath}:/restore/input.db:ro" backend python -c `
    "import os, pathlib, shutil, sqlite3, time; src='/restore/input.db'; dst='/data/stock-chat.db'; tmp='/data/.restore.db'; c=sqlite3.connect(src); result=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); assert result == 'ok', f'Backup integrity check failed: {result}'; shutil.copy2(src, tmp); c=sqlite3.connect(tmp); result=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); assert result == 'ok', f'Restored copy integrity check failed: {result}'; pathlib.Path(dst).exists() and shutil.copy2(dst, f'{dst}.before-restore-{int(time.time())}'); os.replace(tmp, dst); [pathlib.Path(dst + suffix).unlink(missing_ok=True) for suffix in ('-wal','-shm')]"
  if ($LASTEXITCODE -ne 0) { throw 'Restore validation or database replacement failed.' }
}
finally {
  docker compose -f $composeFile up -d backend frontend
}

$healthy = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
  $container = docker compose -f $composeFile ps -q backend
  if ($container) {
    $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $container
    if ($health -eq 'healthy') { $healthy = $true; break }
  }
  Start-Sleep -Seconds 2
}
if (-not $healthy) { throw 'Backend did not become healthy after restore.' }

Write-Host "Database restored from $backupPath"
