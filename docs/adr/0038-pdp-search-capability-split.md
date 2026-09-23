# ADR-0038: Separar Store Search de Product Page Scraping

- Status: Accepted
- Data: 2026-09-23

## Contexto

`BaseStoreSpider` concentrava PDP (`extract_offer` / `extract_details` /
`extract_images`) e Search (`supports_search` / `build_search_url` /
`parse_search_results`). O Product Match (`StoreSearchService`) resolvia o
spider de PDP para descobrir candidatos. Visão VIP evidenciou o problema:
PDP pode ser HTTP-first enquanto a SERP exige Camoufox.

## Problema / decisão necessária

Como desacoplar candidate discovery de scraping de produto para reduzir blast
radius e permitir fetch policies independentes por capability?

## Alternativas consideradas

- **A)** Manter monólito `BaseStoreSpider` (PDP + Search)
- **B)** Dual inheritance (`BaseProductSpider` + `BaseSearchSpider`)
- **C)** Protocol/ABC estreitos + composição + registries independentes
- **D)** Package-by-store (`stores/<key>/{product,search}`) cruzando features

## Decisão

Adotar **C**:

- PDP permanece em `crawler/spiders` (`BaseStoreSpider` só produto)
- Search em `matching/search_adapters` (`StoreSearchAdapter` + `SearchRequest`)
- Registries independentes; `eligible_match_store_keys` =
  `match_enabled` ∩ search registry
- `SearchCandidate` vive em `matching/search_candidate.py`
- `StoreConfig` permanece em `crawler/stores.py` (catálogo compartilhado)
- HtmlFetcher / Camoufox compartilhados; adapters declaram `prefer_browser`

## Justificativa

Menor coupling e blast radius; preserva package-by-feature (ADR 0003);
permite Visão VIP Search `prefer_browser=True` sem alterar PDP; ISP/hexagonal
já usado no projeto (`HtmlFetcher` Protocol).

## Consequências positivas

- Alterar SERP não quebra PDP (e vice-versa)
- Stores podem ter PDP sem Search
- Testes e isolation por capability
- Matching não importa `BaseStoreSpider` para Search

## Trade-offs / consequências negativas

- Mais arquivos (um adapter Search por loja)
- Migração store-by-store exigiu checkpoint de testes
- Catálogo `StoreConfig` ainda no crawler (aceitável; não em `core/`)
