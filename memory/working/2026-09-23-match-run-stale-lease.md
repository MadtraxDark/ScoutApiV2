# MatchRun stale RUNNING — lease vs active (2026-09-23)

## Reprodução controlada (pré-fix)

Cenário simulado (unit/DB, equivalente a power-loss):

1. Criar `ProductMatchRun` com `status=running`, `claim_expires_at` no passado, `attempts=1`.
2. **Antes do fix:** `get_active_for_product` retornava a Run (filtro só por status).
3. Frontend: `isActive` true → timer `now - started_at` crescia sem worker.
4. `POST start` devolvia a mesma Run com `already_active=true`.

## Causa raiz

Lease/heartbeat existiam no worker; **active API ignorava `claim_expires_at`**.

## Política C (implementada)

- Active UX = `pending` OU (`running` + lease válida).
- Worker reclaim se `attempts < max` (skip stores terminais).
- `GET active` com lease expirada → 204 (sem terminalizar; deixa reclaim).
- `POST start` / sweeper exhausted → `failed` + `worker_lost`.
- Timer FE: `active_since` (= `claimed_at` ou `started_at`).
- Fencing: `worker_id` + `attempts` em heartbeat / store outcome / finalize.

## Pós-fix

- [x] GET active stale → None / 204 (`test_stale_running_not_effectively_active_fake_clock`)
- [x] POST start stale → nova Run (`test_start_terminalizes_stale_and_creates_new`)
- [x] Stores terminais preservados (`test_partial_store_preserved_on_outcome`)
- [x] Zombie write rejeitada (`test_zombie_worker_store_outcome_rejected`)
- [x] Reconcile exhausted (`test_reconcile_exhausted_stale_runs`)
- [x] Notification idempotent + alias `STALE_LEASE_EXHAUSTED` → `worker_lost`
- [x] `tests/unit/test_match_runs.py` — 20 passed

## Settings

- `MATCH_RUN_LEASE_SECONDS=600`
- `MATCH_RUN_HEARTBEAT_INTERVAL_SECONDS=120`
- `MATCH_RUN_RECOVERY_INTERVAL_SECONDS=30`
- `MATCH_RUN_MAX_ATTEMPTS=3`
