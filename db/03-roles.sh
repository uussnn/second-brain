#!/bin/sh
# Запускается образом postgres один раз, при создании базы (docker-entrypoint-initdb.d).
set -eu
: "${BOT_DB_PASSWORD:?не задан BOT_DB_PASSWORD}"
: "${WORKER_DB_PASSWORD:?не задан WORKER_DB_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /factory-db/roles.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v bot_pw="$BOT_DB_PASSWORD" -v worker_pw="$WORKER_DB_PASSWORD" <<'SQL'
ALTER ROLE bot_role    PASSWORD :'bot_pw';
ALTER ROLE worker_role PASSWORD :'worker_pw';
SQL
