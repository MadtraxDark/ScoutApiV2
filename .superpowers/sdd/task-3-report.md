# Task 3 — Report: Phase 3 Retry / Attempt Budgets

**Data:** 2026-09-23  
**Status:** CONCLUÍDO ✅

---

## O que foi implementado

### 1. `src/scout_api/modules/matching/attempt_budget.py` (novo)

`StoreAttemptBudget` — dataclass com três contadores independentes e gate methods:

| Método | Semântica | Retorno |
|---|---|---|
| `begin_query()` | Chamado após dedup, antes de emitir a query. Incrementa `queries_used`. | `False` quando budget esgotado → caller para |
| `record_external()` | Cada fetch não-cache que sai para upstream (SERP + candidate scrape). | `False` → skip o request |
| `record_browser_nav()` | Navegação Camoufox real (via hook do StoreSearchService). | `False` → orçamento de browser esgotado |
| `skip_cached()` | Cache/dedup hit — nenhum contador consumido. | `None` |

`stopped_reason`: primeiro motivo de parada é preservado, nunca sobrescrito.

### 2. `src/scout_api/core/config.py` — novos settings

```
match_search_query_budget: int = 5       # MAX, não contagem obrigatória
match_external_attempt_budget: int = 12
match_browser_navigation_budget: int = 8
```

Defaults só aqui e em `.env.example`. Sem hardcode de `5` em outros arquivos.

### 3. `.env.example` — documentação dos novos settings

Bloco adicionado após `MATCH_RUN_*` com os 3 novos parâmetros.

### 4. `src/scout_api/modules/matching/store_search_service.py` — hook de browser nav

Parâmetro `on_browser_nav_used: Callable[[], object] | None = None` adicionado a `search()`.  
Chamado após o fetch quando `request.prefer_browser is True` (sinal de política do adapter).

### 5. `src/scout_api/modules/matching/product_match_service.py` — wiring no store loop

Em `process_one()`:

- **Budget criado** a partir dos settings no início de cada store.
- **`begin_query()`** chamado após dedup, antes de emit/execute — deduped queries não consomem orçamento.
- **SERP não-cache**: `record_external()` → break se esgotado; callback `on_browser_nav_used=budget.record_browser_nav`.
- **SERP cache hit**: `budget.skip_cached()`.
- **Candidate scrape não-cache**: `record_external()` → break inner loop se esgotado; flag `_budget_stop_candidates` propaga break para o query loop.
- **Candidate cache hit**: `budget.skip_cached()`.
- **`store_timing` dict** enriquecido com todos os 7 campos de observabilidade: `queries_used`, `queries_budget`, `external_attempts`, `external_attempt_budget`, `browser_navigations`, `browser_navigation_budget`, `stopped_reason`.

### 6. `tests/unit/test_attempt_budget.py` (novo)

20 testes cobrindo:
- `TestBeginQuery`: limite exato, stop progressivo, budget=0, incremento correto, não incrementa na exaustão
- `TestRecordExternal`: limite, motivo, contador, budget=0
- `TestRecordBrowserNav`: limite, motivo, contador
- `TestSkipCached`: cache hit não consome external nem browser nav; não afeta queries_used
- `TestStrategyABOnOneQuery`: A+B = 1 query, 2 externals; com browser nav
- `TestStoppedReasonPreservation`: primeiro motivo preservado sobre exaustões subsequentes
- `test_settings_have_correct_budget_defaults`: defaults verificados
- `test_budget_from_settings`: construção via settings

---

## Testes

```
tests/unit/test_attempt_budget.py      20 passed
tests/unit/ (suite completa)          768 passed, 0 failed
```

Regressões corrigidas: 3 mock `_search()` em `test_match_store_coverage.py` (linha 227, 329) e `test_matching_regression.py` (linha 1556) precisavam de `**_kwargs: object` para aceitar o novo kwarg `on_browser_nav_used`.

---

## Semânticas respeitadas (spec §2)

| Regra | Implementado |
|---|---|
| SEARCH_QUERY_BUDGET é MAX, não contagem obrigatória | ✅ `begin_query()` para progressivamente |
| Cache/dedup não consome external | ✅ `skip_cached()` no-op; `record_external()` só para não-cache |
| A+B = 1 query, attempts externos separados | ✅ `begin_query()` chamado 1x por query distinta; `record_external()` por fetch |
| stopped_reason observável por store | ✅ no `store_timing` e logs |
| Defaults só em Settings + .env.example | ✅ sem hardcode em outros arquivos |

---

## Limitação conhecida

**Browser nav de candidate scrapes** não é rastreado: `record_browser_nav()` é chamado apenas via hook do `StoreSearchService` (SERP). Para candidate PDPs, `ProductScrapeService` não expõe se Camoufox foi usado. Rastrear isso exigiria refatoração do `ProductScrapeService` (fora do escopo desta task). O `external_attempt_budget` cobre candidate scrapes adequadamente como gate primário.

---

## Pior caso (tabela — ver também working log)

| Caso | queries | external | browser nav |
|---|---|---|---|
| Best | 1 | 1 | 0–1 |
| Normal A→B | 1 | ≤2 | 1 |
| Worst allowed | ≤5 | ≤12 | ≤8 |
| Com proxy fallback | ≤5 | ≤12 | ≤8 (proxy não conta browser nav) |

---

## Pendências restantes

Nenhuma relacionada a esta task.

Limitação de candidate-level browser nav tracking documentada acima (não é pendência aberta — é limitação aceita de escopo).
