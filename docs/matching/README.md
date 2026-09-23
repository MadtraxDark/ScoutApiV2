# Product Match — Store Search vs PDP

Product Match **compõe** duas capabilities independentes (ADR 0038):

1. **Store Search** (`matching/search_adapters`) — descobre `SearchCandidate`
2. **Product Scraping** (`crawler/spiders` + `ProductScrapeService`) — interpreta PDP

```text
ProductMatchService
  → StoreSearchService → StoreSearchAdapter → SearchCandidate[]
  → ProductScrapeService → BaseStoreSpider (PDP)
  → ProductIdentity → ProductMatcher
```

## Adicionar loja

| Objetivo | O que implementar |
|---|---|
| Só crawl/oferta | Spider PDP em `crawler/spiders/` + `StoreConfig` |
| Participar do Match | **Também** `StoreSearchAdapter` em `matching/search_adapters/` |

Não implemente SERP dentro do spider PDP. Não implemente `extract_offer` no Search adapter.

## Eligibility

```text
eligible = match_enabled ∩ registered_search_store_keys()
```

Fonte de Search: `matching/search_adapters/registry.py` — **não** `supports_search` no spider.

## Contratos

- `SearchRequest` — URL (+ `prefer_browser`)
- `StoreSearchAdapter` — `build_search_request` / `parse_candidates` / `classify_empty_result`
- `SearchCandidate` — `matching/search_candidate.py`

## Budgets por loja (StoreAttemptBudget)

Cada loja dentro de um `MatchRun` opera sob três budgets independentes
(módulo `matching/attempt_budget.py`):

| Budget | Padrão env var | Propósito |
|---|---|---|
| `queries_budget` | `MATCH_SEARCH_QUERY_BUDGET=5` | Queries progressivas máximas por loja |
| `external_attempt_budget` | `MATCH_EXTERNAL_ATTEMPT_BUDGET=12` | Requests upstream (SERP + PDPs) |
| `browser_navigation_budget` | `MATCH_BROWSER_NAVIGATION_BUDGET=8` | Navegações Camoufox reais |

Regras:
- Strategy A + B na mesma query = 1 `begin_query()`; cada request upstream = 1 `record_external()`.
- Cache/dedup hits: `skip_cached()` — não consomem budget.
- Budget esgotado: store encerra progressão; Run continua nas outras stores.
- `stopped_reason` preserva o primeiro motivo de parada por loja (observabilidade de log).

## Concorrência de browser (BrowserScheduler)

O `BrowserScheduler` limita o número de slots Camoufox simultâneos:

- `CAMOUFOX_BROWSER_CAPACITY=1` em produção (decisão C1 — ADR 0039).
- Fila saturada → `RequestError(code="BROWSER_QUEUE_SATURATED")` em vez de hang.
- `ProfileLock` (Redis primary, fcntl fallback) previne dois processos abrindo
  o mesmo diretório de perfil simultaneamente.
- `BrowserCircuitBreaker.claim_trial()`: token atômico no estado HALF_OPEN
  garante singleflight (sem thundering herd de launch).
- Failure domains: circuit por store key; falha de infra (launch) ≠ `NO_MATCH`.

Ver ADR 0037 (launch health + fail-fast) e ADR 0039 (bounded scheduler C1).
