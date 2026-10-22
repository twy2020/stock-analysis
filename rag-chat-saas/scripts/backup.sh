#!/usr/bin/env sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output=${1:-"$project_root/backup-stock-chat-$(date +%Y%m%d-%H%M%S).db"}
temp="/data/backup-$(date +%s)-$$.db"

cd "$project_root"
container=$(docker compose ps -q backend)
if [ -z "$container" ]; then
  echo 'Backend container is not running.' >&2
  exit 1
fi

cleanup() {
  docker compose exec -T backend rm -f "$temp" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose exec -T backend python -c "import sqlite3; s=sqlite3.connect('/data/stock-chat.db'); d=sqlite3.connect('$temp'); s.backup(d); d.close(); s.close()"
docker cp "$container:$temp" "$output"
echo "Backup written to $output"
