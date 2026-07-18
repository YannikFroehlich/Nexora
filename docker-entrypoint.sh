#!/bin/sh
set -e

sqlite_path="${SQLITE_PATH:-/app/data/db.sqlite3}"
data_dir="$(dirname "$sqlite_path")"

mkdir -p "$data_dir"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"
