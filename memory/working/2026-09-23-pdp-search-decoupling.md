# Working log — PDP / Store Search decoupling (ADR 0038)

Date: 2026-09-23

## Baseline (pre)

- 13 spiders: PDP + Search same class (`supports_search=True`)
- `StoreSearchService` → `resolve_spider_by_store_key` + spider search methods
- `eligible_match` ← `stores_supporting_search()` (spider flag)
- `SearchCandidate` in `crawler/models/search.py`
- Visão VIP: SERP Camoufox required; PDP HTTP payload sufficient

## Decision

Approach C: `StoreSearchAdapter` under `matching/search_adapters/` + PDP spiders only.

## After

- Search adapters: 13 stores registered
- `StoreSearchService` uses registry only (no `BaseStoreSpider`)
- `eligible_match_store_keys` in `matching/eligibility.py`
- `SearchCandidate` → `matching/search_candidate.py`
- Visão VIP Search `prefer_browser=True`; PDP spider has no search methods
- Architecture tests: `tests/unit/test_search_pdp_boundaries.py`
- Shell classification tests: `tests/unit/test_store_search_service.py`
- ADR 0038 + `docs/matching/README.md`

## Commands / evidence

- Registry discovery lists 13 keys including `visaovip`
- `pytest` boundaries + store_search_service + contracts + visaovip + parsers + match coverage + matching_regression + amazon_match_display: **161 passed**
- Store PDP suites (kabum/pichau/nissei/bestbuy/ml/aliexpress/shoppingchina): **78 passed**
- `ruff check` on changed matching/search + boundaries: clean
- Performance: unit suites unchanged order of magnitude (~1.7s / ~0.5s); no extra fetch duplication introduced (shared HtmlFetcher retained)

## Pendências restantes

- nenhuma desta tarefa (PENDING-016/017 ML-Shopee match_enabled permanecem fora do escopo)

