# Camoufox launch health + Match fail-fast — working log

Date: 2026-09-23

## Before (evidence from prior MatchRun)

- Entrypoint: `chown -R` on bind `./data/camoufox-profiles` → mass `Input/output error`
- Playwright launch timeout default 180_000 ms (no `timeout=` in launch kwargs)
- Classified as `UPSTREAM_REQUEST_ERROR`; Match continued queries/stores
- Wall: `product_match_run_job` ≈ 2_042_678 ms (~34 min)
- Sandbox EPERM / glxtest / dbus-launch warnings present

## Changes landed

- `docker-entrypoint.sh`: no recursive chown; optional `root-only`; purge disposable caches
- `CAMOUFOX_LAUNCH_TIMEOUT_MS` (45s) + circuit breaker (`browser_health`)
- Match fail-fast on `BROWSER_*`; identity-first reference when catalog has title
- ADR 0037 + `docs/performance.md` + compose/env + `dbus-x11` in Dockerfile

## After (Docker Compose rebuild 2026-09-23)

### Boot

- `camoufox_disposable_cache_purged: root=.../camoufox-profiles` present on api + match-runner
- No `chown` / `Input/output error` flood in logs
- Alembic + Uvicorn started normally

### Camoufox min probe (`-u app`)

| locale | browser_launch_ms | navigation_ms | result |
|---|---:|---:|---|
| locale_default | 2750.5 | 34.2 | ok |
| locale_pt_br | 2264.1 | 41.9 | ok |
| locale_en_us | 1745.2 | 117.2 | ok |

Note: `docker compose exec` without `-u app` runs as root and fails fast (~0.4–0.7s)
with HOME ownership message — not a hang. App runtime uses `runuser -u app`.

### CamoufoxHtmlFetcher

- Kabum homepage: ~12.8s, status 200, launches=1, circuit=healthy

### Limited Match live (identity-first, stores=pichau/terabyteshop/magazineluiza)

- elapsed_ms ≈ 144_529 (~2.4 min) — searches completed; circuit stayed healthy
- outcomes: all `no_match` (no BROWSER_*); ERROR≠NO_MATCH path covered by unit tests
- Before: ~34 min with N×180s launch hangs

### Unit tests

- `test_browser_health`, `test_match_store_coverage` (BROWSER fail-fast),
  `test_match_runs` (identity-first), `test_docker_entrypoint_camoufox`

## Pendências

- PENDING-016 (Shopee wall) permanece separado — Shopee ainda `match_enabled=false`
  (PENDING-017). Esta root cause (Camoufox launch/chown) está resolvida.
