# Working log — Match-runner hang watchdog

Date: 2026-09-23

## Objetivo

Eliminar pending eterno quando match-runner trava em hang nativo.

## Baseline

- Sintoma: POST match-runs 202; run fica pending; worker Camoufox silencioso.
- Causa: single-thread `process_claimed_run` hang → claim loop parado.
- Compose: `restart: unless-stopped`; entrypoint `exec runuser -u app -- "$@"`.
- PID1: `runuser` após `exec`; exit do Python propaga para Docker.

## Implementação

- `match_hang_constants.py` — exit 78, STORE_WALL_TIMEOUT, RUN_WALL_TIMEOUT
- `match_progress.py` — ProgressTracker (heartbeat ≠ progress)
- `match_deadlines.py` — MonotonicDeadline + capped_timeout
- `match_watchdog.py` — daemon stale check + expire lease + os._exit(78)
- Wired em `match_run_worker` + `product_match_service`
- Settings + compose + .env.example

## Defaults finais

| Setting | Default |
|---|---|
| MATCH_STORE_WALL_TIMEOUT_SECONDS | 180 |
| MATCH_RUN_WALL_TIMEOUT_SECONDS | 2700 |
| MATCH_RUN_WATCHDOG_STALE_SECONDS | 600 |
| MATCH_RUN_WATCHDOG_ENABLED | true |
| MATCH_WORKER_HANG_EXIT_CODE | 78 |

Nenhum default alterado vs design aprovado.

## Testes

- Unit ProgressTracker/watchdog: 16+ passed
- Wall timeouts fake-clock: 2 passed
- test_match_runs: passed (assinatura fake_execute atualizada)
- Total alvo hang/wall/runs: 39 passed

## Docker restart

- MATCH_RUN_TEST_INJECT_HANG=true + STALE=20s
- Run A claimed → inject hang → watchdog_stale/exit ~22s após arm
- RestartCount incrementou; lease expirada pelo watchdog (claim_expires_at ≈ exit)
- Sem inject: Run A reclaim attempt=2 e processou lojas (kabum/shoppingchina/amazon_br no_match)
- Run B ficou enfileirada (batch=1) até A liberar — não PENDING eterno por hang do worker

## Timings observados

- Watchdog stale 20s → exit ≈22s após claim (check interval 2s)
- Container restart <1s após exit
