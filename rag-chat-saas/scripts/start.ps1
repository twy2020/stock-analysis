$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '../../scripts/start-stock.ps1')
exit $LASTEXITCODE
