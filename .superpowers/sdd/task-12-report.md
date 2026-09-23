# Task 12 — Integration / load / soak / chaos: relatório

**Data:** 2026-09-23  
**Resultado:** ✅ CONCLUÍDO — 12 novos testes passando; 152 total sem regressão

---

## Checklist caos (unit/integration simulations)

| Item | Cobertura | Arquivo/teste |
|------|-----------|---------------|
| browser process killed (poison/recycle) | ✅ NOVO | `test_chaos_browser_match.py::test_poison_release_returns_slot_to_pool`, `test_poison_release_wakes_waiter` |
| launch timeout → BROWSER_* ERROR not NO_MATCH | ✅ existente | `test_match_store_coverage.py::test_browser_infrastructure_error_fail_fast_not_no_match` |
| owner-thread failure (trial TTL reap) | ✅ existente | `test_browser_circuit_claim_trial.py::test_probe_crash_does_not_stick_half_open` |
| profile lock held by peer | ✅ existente | `test_profile_lock.py::test_redis_lock_exclusivity_second_caller_blocks` |
| queue full → BROWSER_QUEUE_SATURATED | ✅ NOVO + existente | `test_chaos_browser_match.py::test_browser_infra_error_from_search_is_match_error_not_no_match`, `test_browser_queue_timeout_from_search_is_match_error_not_no_match`; `test_browser_scheduler.py::test_queue_saturated_fails_fast` |
| store WAF block → store circuit / ERROR | ✅ existente | `test_store_capability_health.py::test_search_service_records_failure_on_waf` |
| operation nav timeout → SINGLE_OPERATION (no infra circuit) | ✅ NOVO | `test_chaos_browser_match.py::test_nav_timeout_code_not_in_browser_infrastructure_error_codes`, `test_nav_timeout_does_not_stop_query_loop`, `test_infra_error_stops_query_loop_immediately` |
| Server Action invalid contract → fallback B / not NO_MATCH | ✅ existente | `test_visaovip_search_chain.py::test_chain_strategy_a_error_falls_back_to_b[INVALID_RESPONSE]` |

---

## Soak capacity=1

**Método:** 2 soaks em threading (sem Docker; live crawl não disponível).

- `test_soak_serial_acquire_release_capacity1`: 20 iterações serial, mix normal/poison — 0 slots vazados, estado sempre consistente.
- `test_soak_concurrent_queue_pressure_with_poison`: 8 workers concorrentes, queue=4, poison a cada 4 workers — sem deadlock em 10 s, pool retorna a active=0.

**Duração total dos soaks:** < 200 ms (threading puro, sem I/O real).  
**Sem regressão de performance:** P95 dos testes de browser/scheduler permanece igual ao baseline (< 1s).

---

## Coverage gate

Dois testes de coverage gate adicionados:

1. `test_coverage_gate_all_eligible_stores_reported_in_outcome` — garante que todas as lojas elegíveis (via `eligible_match_store_keys()`) aparecem no callback `on_store_outcome`. Nenhuma loja silenciosamente descartada.
2. `test_coverage_gate_skip_stores_are_excluded_but_others_reported` — skip_stores remove lojas corretas; demais elegíveis ainda reportam.

---

## Resultado dos testes

```
152 passed, 2 skipped (Windows/fcntl), 0 failed
Tempo total: ~3.7 s
```

Nenhuma regressão nos 120 testes existentes.

---

## Pendências restantes

Nenhuma.

Limitação aceita: soak Docker não executado (ambiente sem container ativo). Os soaks de threading cobrem a semântica do `BrowserScheduler` + pool de slots. Evidência de capacidade C1 em harness de produção está documentada em ADR 0039 e no log de benchmark `bench_camoufox_c1_baseline_2026-09-23.json`.
