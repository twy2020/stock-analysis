#!/usr/bin/env sh
set -eu
stock_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$stock_root"
python3 scripts/bootstrap_stock.py
docker compose --env-file .stock-private/stock.env up -d --build
echo 'Open http://127.0.0.1:18110/'
