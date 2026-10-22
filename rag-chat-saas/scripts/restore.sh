#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/backup.db" >&2
  exit 2
fi

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup=$1
data_volume=stock-analysis-chat-data

if [ ! -f "$backup" ]; then
  echo "Backup file not found: $backup" >&2
  exit 1
fi
backup_dir=$(CDPATH= cd -- "$(dirname -- "$backup")" && pwd)
backup="$backup_dir/$(basename -- "$backup")"

cd "$project_root"
docker volume inspect "$data_volume" >/dev/null
docker compose stop backend
restore_status=0
docker compose run --rm --no-deps \
  --volume "$backup:/restore/input.db:ro" backend python -c \
  "import os, pathlib, shutil, sqlite3, time; src='/restore/input.db'; dst='/data/stock-chat.db'; tmp='/data/.restore.db'; c=sqlite3.connect(src); result=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); assert result == 'ok', f'Backup integrity check failed: {result}'; shutil.copy2(src, tmp); c=sqlite3.connect(tmp); result=c.execute('PRAGMA quick_check').fetchone()[0]; c.close(); assert result == 'ok', f'Restored copy integrity check failed: {result}'; pathlib.Path(dst).exists() and shutil.copy2(dst, f'{dst}.before-restore-{int(time.time())}'); os.replace(tmp, dst); [pathlib.Path(dst + suffix).unlink(missing_ok=True) for suffix in ('-wal','-shm')]" || restore_status=$?
docker compose up -d backend frontend
if [ "$restore_status" -ne 0 ]; then
  echo 'Restore validation or database replacement failed.' >&2
  exit "$restore_status"
fi

attempt=0
while [ "$attempt" -lt 30 ]; do
  container=$(docker compose ps -q backend)
  if [ -n "$container" ]; then
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
    if [ "$health" = healthy ]; then
      echo "Database restored from $backup"
      exit 0
    fi
  fi
  attempt=$((attempt + 1))
  sleep 2
done

echo 'Backend did not become healthy after restore.' >&2
exit 1
