# Task 0 — Phase 0 Baseline / reproduction

**Date:** 2026-09-23  
**Status:** DONE  
**Commits:** none (per user rule)

## Scope

Measurement-only baseline for Camoufox C1 (current code) before scheduler/capacity work. No production crawler/match behavior changes beyond new bench skeleton and working log.

## Step 1 — Versions

Executed in running `match-runner` container:

```text
camoufox 0.5.6
playwright 1.62.0
python /usr/local/bin/python
```

Camoufox browser bundle path (pkgman `camoufox_path()`):

```text
/home/app/.cache/camoufox/browsers/official/152.0.4-beta.30-5720d45b
```

Host `.venv` matches: camoufox 0.5.6, playwright 1.62.0.

## Step 2 — C1 minimal infra baseline

Harness: `scripts/bench_camoufox_capacity.py` (`--capacity 1`, `--iterations 10`).

Run (isolated profile under `/tmp`, bind-mount scripts/src because image lacks uncommitted files):

```text
docker compose run --rm --no-deps -v ./scripts:/app/scripts:ro -v ./src:/app/src:ro api \
  python scripts/bench_camoufox_capacity.py --capacity 1 --iterations 10
```

Target URL: `https://example.com/` (cheap stable navigation).

| Metric | Value |
|---|---|
| browser_launches | 1 |
| browser_reuses | 9 |
| browser_launch_failures | 0 |
| fetch wall P50 | 809.8 ms |
| fetch wall P95 | 3400.0 ms |
| fetch wall max | 5462.9 ms (iter 1 cold launch) |
| RSS VmRSS start / peak / end | 68020 / 138488 / 138556 KB |
| success rate | 10/10 |

Artifact: `memory/working/bench_camoufox_c1_baseline_2026-09-23.json`.

**observe() note:** `html_fetcher.py` records `browser_launch` and `browser_reuse` via `scout_api.core.performance.observe`; fetcher counters are the authoritative baseline for launch/reuse in this run.

**Duration:** ~20 s wall for full bench container run (10 fetches + image entrypoint/migrate overhead).

## Step 3 — Process topology

Documented in `memory/working/2026-09-23-camoufox-visaovip-reliability.md`:

- Match Search → `match-runner`
- PDP refresh → `monitor`
- Shared profiles → `./data/camoufox-profiles` on api + monitor + match-runner
- Distributed store circuit: **not** started (per task)

## Deliverables

| Item | Path |
|---|---|
| Working log baseline | `memory/working/2026-09-23-camoufox-visaovip-reliability.md` |
| Bench skeleton | `scripts/bench_camoufox_capacity.py` |
| JSON results | `memory/working/bench_camoufox_c1_baseline_2026-09-23.json` |

## Self-review

- Bench script stays read-only on production paths (default `/tmp/scout-bench-camoufox-capacity`); C2/C3 stub returns note without fake metrics.
- No Search/PDP coupling touched.
- No git commit.
- `capacity` 2/3 correctly deferred to Task 5.

## Concerns / limitations

1. C1 run used **isolated** `/tmp` profile, not the shared bind mount — avoids lock contention with live `match-runner`/`monitor` while still exercising current `CamoufoxHtmlFetcher` warm-reuse code path.
2. Bench required **volume-mount** of `scripts/` and `src/` into one-off `api` run; baked image does not include new script until rebuild.
3. P95 includes cold-start iteration 1; warm-only P50 ~810 ms is the steady-state signal.
4. `match-runner`/`monitor` healthchecks show unhealthy in `docker compose ps` during session; baseline did not depend on those workers.

## Performance impact

No production code path changed. One-off measurement ~20 s in disposable container.

## Pendências restantes

Nenhuma para Task 0. Próximo: Task 1 (BrowserScheduler C1 hardening) per plan.
