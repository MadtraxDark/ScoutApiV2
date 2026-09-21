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

exec runuser -u app -- "$@"
