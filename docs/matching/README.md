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

## Geração de queries

`ProductIdentity` gera queries progressivas a partir de identificadores e frases
comerciais reconhecidas. Quando não há frase específica para a categoria, um
modelo estruturado alfanumérico (letras e números) também é preservado como
chave de descoberta; a validação posterior continua sob responsabilidade do
matcher e dos gates de variante.

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

## Hang defense-in-depth (match-runner)

Uma MatchRun travada **não** pode bloquear o único worker indefinidamente.

| Camada | Setting | Default | Efeito |
|---|---|---|---|
| Store wall | `MATCH_STORE_WALL_TIMEOUT_SECONDS` | 180 | Deadline absoluto por loja (monotonic). Estouro → store `error` `STORE_WALL_TIMEOUT` (nunca `NO_MATCH`). Run continua. |
| Run wall | `MATCH_RUN_WALL_TIMEOUT_SECONDS` | 2700 | Desde claim/processamento (PENDING não conta). Estouro → run `failed` `RUN_WALL_TIMEOUT`. |
| Watchdog | `MATCH_RUN_WATCHDOG_STALE_SECONDS` | 600 | Sem **progresso real** → `os._exit(78)` + Docker restart + reclaim ADR 0036. |
| Flag | `MATCH_RUN_WATCHDOG_ENABLED` | true | Rollback operacional. |
| `0` nos timeouts numéricos | — | desliga aquela camada. |

**Heartbeat ≠ progresso.** Lease heartbeat renova ownership; `ProgressTracker.mark_progress`
só em eventos observáveis (store start, search, candidates, scrape, match/no_match/error).

Exit code documentado: `MATCH_WORKER_HANG_EXIT_CODE = 78`.

Labels UI (PriceScout): mapear códigos para pt-BR — nunca exibir snake_case cru
(`STORE_WALL_TIMEOUT` → “A busca nesta loja excedeu o tempo limite.”;
`RUN_WALL_TIMEOUT` → “A execução excedeu o tempo máximo.”;
`worker_lost` → “Busca anterior foi interrompida.”).

Ver emenda em ADR 0036.
