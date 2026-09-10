#!/bin/sh
set -eu

PROFILE_DIR="${CAMOUFOX_USER_DATA_DIR:-/home/app/.cache/scout-api/camoufox-profiles/default}"
PROFILE_ROOT="$(dirname "$PROFILE_DIR")"

mkdir -p "$PROFILE_DIR"
# Named volumes are root-owned by default; the API runs as non-root `app`.
chown -R app:app "$PROFILE_ROOT"

exec runuser -u app -- "$@"
