# Design: Match-runner hang watchdog (híbrido)

- Data: 2026-09-23
- Status: Approved (execução ponta a ponta)
- Relacionado: ADR 0036, `docs/matching/README.md`

## Problema

Worker single-thread: hang nativo (Camoufox/Playwright) em `process_claimed_run`
impede o loop de claim → novas MatchRuns ficam `pending` indefinidamente.

## Camadas

| Camada | Setting | Default | Semântica |
|---|---|---|---|
| Store wall | `MATCH_STORE_WALL_TIMEOUT_SECONDS` | 180 | Deadline absoluto por loja (monotonic). Estouro → store `error` `STORE_WALL_TIMEOUT`. Run continua. |
| Run wall | `MATCH_RUN_WALL_TIMEOUT_SECONDS` | 2700 | Deadline desde claim/processamento (não conta PENDING). Estouro cooperativo → run `failed` `RUN_WALL_TIMEOUT`. |
| Watchdog stale | `MATCH_RUN_WATCHDOG_STALE_SECONDS` | 600 | Sem **progresso real** → `os._exit(78)`. Independente do lease. |
| Watchdog enable | `MATCH_RUN_WATCHDOG_ENABLED` | true | Rollback operacional. |
| `0` | — | desliga o timeout/watchdog numérico correspondente. |

## Heartbeat ≠ progresso

- Lease heartbeat: liveness/ownership apenas.
- `last_progress_monotonic`: só eventos de avanço observável via `ProgressTracker.mark_progress`.

## Hard exit

- Constante `MATCH_WORKER_HANG_EXIT_CODE = 78`.
- Docker: entrypoint `exec runuser …` → exit do Python propaga; `restart: unless-stopped` reinicia; reclaim ADR 0036.

## Error codes

- Store: `STORE_WALL_TIMEOUT` (nunca `NO_MATCH`)
- Run: `RUN_WALL_TIMEOUT` (nunca `completed`)
- Pós-kill: recovery via lease → `worker_lost` conforme ADR 0036

## Test-only hang inject

`MATCH_RUN_TEST_INJECT_HANG=true` rejeitado quando `ENVIRONMENT=production`.
