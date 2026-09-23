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
