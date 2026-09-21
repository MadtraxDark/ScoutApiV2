#!/bin/sh
set -eu

# Host shell env often overrides Compose .env with localhost; rewrite loopback
# to the Compose Postgres service hostname when the API runs in-container.
# Pattern is *@localhost: (user:password@host), not *:@localhost:.
if [ -n "${DATABASE_URL:-}" ]; then
  case "$DATABASE_URL" in
    *@localhost:*|*@127.0.0.1:*|*@localhost/*|*@127.0.0.1/*)
      DATABASE_URL=$(
        printf '%s' "$DATABASE_URL" \
          | sed \
            -e 's/@localhost:/@postgres:/g' \
            -e 's/@127.0.0.1:/@postgres:/g' \
            -e 's/@localhost\//@postgres\//g' \
            -e 's/@127.0.0.1\//@postgres\//g'
      )
      export DATABASE_URL
      ;;
  esac
fi

PROFILE_DIR="${CAMOUFOX_USER_DATA_DIR:-/home/app/.cache/scout-api/camoufox-profiles/default}"
PROFILE_ROOT="$(dirname "$PROFILE_DIR")"

mkdir -p "$PROFILE_DIR"
# Named volumes are root-owned by default; the API runs as non-root `app`.
chown -R app:app "$PROFILE_ROOT"

# Apply pending schema migrations before API/workers start.
# Concurrent container starts are safe (Alembic Postgres advisory lock).
# Disable with AUTO_MIGRATE=false when a one-shot migrate job already ran.
_should_migrate=1
case "${AUTO_MIGRATE:-true}" in
  0|false|False|FALSE|no|No|NO|off|Off|OFF) _should_migrate=0 ;;
esac
if [ "$_should_migrate" -eq 1 ] && [ -n "${DATABASE_URL:-}" ]; then
  echo "alembic_upgrade_head: starting"
  runuser -u app -- alembic upgrade head
  echo "alembic_upgrade_head: done"
fi

exec runuser -u app -- "$@"
