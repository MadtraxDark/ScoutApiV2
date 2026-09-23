# Task 11 Report — Phase 11: Store + capability circuit

**Status:** DONE

## Implementado

- `src/scout_api/modules/crawler/core/store_capability_health.py`
  - `StoreCapabilityCircuit`: CLOSED/OPEN/HALF_OPEN + `claim_trial` / `complete_trial` / `record_failure` / `record_success` + TTL reap
  - Chave por `(store_key, capability)` — search e product_scrape são completamente independentes
  - `is_store_search_trip_failure()`: trip apenas em `UPSTREAM_WAF_BLOCKED`, `UPSTREAM_BLOCKED`, `SEARCH_INCOMPLETE_RESPONSE`, `OSError/ConnectionError`
  - `ParseError` isolado, resultado vazio e rejeição do matcher **NÃO** tripam o circuit
  - Registro process-local; `reset_store_capability_circuits_for_tests()` para isolamento de testes
- `src/scout_api/core/config.py` — 3 novas settings: `store_capability_circuit_enabled`, `_failure_threshold`, `_cooldown_seconds`
- `.env.example` — novas variáveis documentadas com rollback flag
- `src/scout_api/modules/matching/store_search_service.py`
  - `search()` verifica o circuit antes de buscar; `_search_inner()` executa a lógica original
  - WAF/connection failures → `record_failure()` ou `complete_trial(success=False)`
  - Sucesso → `record_success()` ou `complete_trial(success=True)`
  - Circuit OPEN no `search` não toca `product_scrape`
- `tests/unit/test_store_capability_health.py` — 28 testes, todos verdes

## Testes

```
28 passed (0.13s)   # apenas test_store_capability_health
125 passed (1.30s)  # + browser_health + claim_trial + match regressions
```

## Pendências restantes

Nenhuma.
