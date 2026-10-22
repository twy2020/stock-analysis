$ErrorActionPreference = 'Stop'
$stockRoot = Split-Path -Parent $PSScriptRoot
Push-Location $stockRoot
try {
  & "$stockRoot/agent-core/.venv/Scripts/python.exe" scripts/bootstrap_stock.py
  if ($LASTEXITCODE -ne 0) { throw 'Stock configuration failed.' }
  & "$stockRoot/agent-core/.venv/Scripts/python.exe" scripts/configure_stock_web.py
  if ($LASTEXITCODE -ne 0) { throw 'Stock web configuration failed.' }
  if (Test-Path "$stockRoot/.stock-private/market-relay.enabled") {
    try {
      $relay = Invoke-RestMethod -Uri 'http://127.0.0.1:18766/health' -TimeoutSec 5
      if ($relay.service -ne 'stock-market-relay' -or $relay.status -ne 'UP') {
        throw 'Unexpected relay identity or market upstream unavailable.'
      }
    } catch {
      throw 'Start the stock market relay dependency in Service Hub first; port 18766 must report stock-market-relay UP.'
    }
    $env:MARKET_API_URL = 'http://host.docker.internal:18766/api/db'
    $env:MARKET_API_TOKEN_FILE = '/run/stock/engine.token'
  }
  docker compose --env-file .stock-private/stock.env up -d --build
  if ($LASTEXITCODE -ne 0) { throw 'Stock deployment failed.' }
  docker compose --env-file .stock-private/stock.env ps
  Write-Host 'Stock chat: http://127.0.0.1:18110/'
  Write-Host 'Stock Core console: http://127.0.0.1:18210/admin'
} finally { Pop-Location }
