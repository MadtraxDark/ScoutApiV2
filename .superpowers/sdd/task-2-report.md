# Task 2 Report — Phase 2: Half-open single-flight

**Status:** ✅ DONE — 728 testes passando, sem regressões.

---

## O que foi implementado

### `browser_health.py` — BrowserCircuitBreaker hardened

- **Máquina de estados completa:**
  - `HEALTHY` (CLOSED) → `allow()` True
  - `UNAVAILABLE` (OPEN) → `allow()` False (fail-fast)
  - `DEGRADED` (HALF_OPEN) → `allow()` False; `claim_trial()` concede UM token atômico
- **`TrialToken`** — dataclass com `token_id` (UUID) e `expires_at`
- **`claim_trial(now=...)`** — atômico sob `threading.Lock`; retorna token para exatamente 1 caller em HALF_OPEN; demais recebem `None` → fail-fast
- **`complete_trial(token, success=bool, now=...)`** — success → CLOSED; failure → OPEN + novo cooldown; token reaped (TTL expirado) → no-op
- **`_reap_expired_trial_unlocked(now=...)`** — se trial TTL expirar sem `complete_trial()`, reabre circuit (UNAVAILABLE) com novo cooldown; HALF_OPEN não fica preso para sempre
- **`allow()` agora retorna `False` para DEGRADED** (breaking change semântico intencional; testes existentes corrigidos)
- **`TRIAL_TTL_SECONDS = 120`** — default configurável por constructor
- **`snapshot()`** agora inclui `active_trial` e `active_trial_expires_at`
- **`BROWSER_INFRASTRUCTURE_ERROR_CODES`** agora inclui `BROWSER_QUEUE_SATURATED`, `BROWSER_QUEUE_TIMEOUT`, `BROWSER_JOB_CANCELLED` (queue infra = browser infra para Match fail-fast)

### `exceptions.py`

- `BROWSER_INFRASTRUCTURE_ERROR_CODES` sincronizada com os mesmos 5 códigos.

### `html_fetcher.py` — wiring claim_trial / complete_trial

- **`_acquire_browser`**: se `allow()` False → tenta `claim_trial()`; token None → fail-fast + incrementa `_browser_circuit_open_hits`; token recebido → probe; `complete_trial(success=True/False)` no local correto (sem `finally` global para evitar double-complete)
- **`_fetch_locked` (oneshot path)**: mesma lógica para AliExpress oneshot
- `record_success()` / `record_launch_failure()` continuam sendo chamados no caminho HEALTHY normal

### `tests/unit/test_browser_circuit_claim_trial.py` — 13 novos testes

| Teste | Cobertura |
|---|---|
| `test_closed_allow_true` | HEALTHY → allow True |
| `test_open_allow_false` | OPEN → allow False |
| `test_half_open_allow_false` | HALF_OPEN → allow False (não HALF_OPEN grant) |
| `test_claim_trial_returns_none_when_healthy` | claim_trial() em HEALTHY → None |
| `test_claim_trial_returns_none_when_open` | claim_trial() em OPEN → None |
| `test_success_closes_circuit` | complete_trial(success=True) → CLOSED |
| `test_failure_reopens_and_resets_cooldown` | complete_trial(success=False) → OPEN + novo cooldown |
| `test_non_probe_fail_fast_does_not_wait` | 2º e 3º claim_trial() → None imediato |
| `test_probe_crash_does_not_stick_half_open` | TTL expirado → reopen UNAVAILABLE |
| `test_ten_callers_one_probe` | 10 threads simultâneos → exatamente 1 token |
| `test_complete_trial_stale_token_is_noop` | token reaped → complete_trial no-op |
| `test_snapshot_includes_trial_fields` | snapshot contém active_trial / expires_at |
| `test_queue_codes_in_infrastructure_error_codes` | SATURATED/TIMEOUT/CANCELLED nos códigos |

### `tests/unit/test_browser_health.py` — 2 testes atualizados

- `test_circuit_opens_on_launch_failure_not_page_timeout`: corrido para usar `claim_trial()` em vez de `allow()` em HALF_OPEN
- `test_cooldown_probe_window`: idem

---

## Evidência RED → GREEN

**RED (antes da implementação):** testes de `claim_trial` não existiam; os dois testes de `test_browser_health` passavam mas com semântica errada (HALF_OPEN = allow True).

**GREEN:** 728/728 testes passando após implementação.

```
tests/unit/test_browser_circuit_claim_trial.py  13 passed
tests/unit/test_browser_health.py               6 passed
tests/unit/test_browser_scheduler.py            7 passed
(demais 702 testes)                            702 passed
Total: 728 passed, 0 failed
```

---

## Observações / Concerns

1. **`state` e `snapshot()` sem `now`**: ambos usam `datetime.now(UTC)` internamente. Em testes com datas passadas (T0 < now real), `_maybe_half_open_unlocked` dispara com o relógio real, causando transição prematura. Solução no test_browser_circuit_claim_trial.py: `T0 = datetime(2030, ...)` (futuro). Concern cosmético, não funcional.

2. **Warm session + probe token**: se `claim_trial()` retorna token mas a warm session ainda está viva (caso de borda improvável após falha de launch), `complete_trial(success=True)` é chamado. Correto — browser vivo = evidência de saúde.

3. **Performance**: nenhuma operação ficou mais lenta. `test_ten_callers_one_probe = 0.002s`.

---

## Pendências restantes

Nenhuma relacionada à Task 2. A Task 2 está **RESOLVIDA POR COMPLETO**.
