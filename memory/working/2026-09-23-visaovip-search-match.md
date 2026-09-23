# Working log — Visão VIP Product Match search gap

Date: 2026-09-23
Product: `0cb47f6a-298b-441d-9154-e33a37d75cd5`
Ground truth (evidence only):
`https://www.visaovip.com/prod/placas-mae-amd/placa-mae-asus-tuf-gaming-b650m-e-wi-fi-socket-am5-ddr5/41749/`

## Baseline (pre-search)

- Visão VIP: `supports_search=False` → **omitted** from `eligible_match_store_keys`
- Classification: **SEARCH_ENDPOINT_FAILURE / RETRIEVAL_FAILURE** (store never searched)
- Not MATCH_FAILURE — correct PDP never entered the candidate set

## Real storefront search

| Probe | Result |
|---|---|
| `GET /busca/?q=…` | soft 404 |
| `GET /busca/termo/{slug}/` | real SERP (spaces → hyphens) |
| Plain HTTP | **403**, 0 candidates |
| Camoufox (default fetcher) | ~7s, hydrated `/prod/…/{code}/` cards; ground truth present |

## Fix (generic)

1. `VisaoVipSpider.supports_search=True`
2. `build_search_url` → `/busca/termo/{slug}/`
3. `parse_search_results` via stable `/prod/.../{id}/` href (skip CDN gallery)
4. Incomplete SERP shell → `UPSTREAM_BLOCKED` (ERROR ≠ NO_MATCH)
5. Shared progressive motherboard queries (already in `build_search_queries`)

## After fix — live Visão VIP-only Match

- `gt_discovered=true`
- URL: `…/41749/` discovered via query `asus tuf gaming b650m-e wifi`
- decision `auto_match` (`brand_match`, `brand_model_exact`, `title_similarity`)
- price `U$ 171.00` / `USD`, product_id `41749`
- wall ~17.5s (Kabum ref scrape + Camoufox SERP + PDP)
- listing persisted on canonical `0cb47f6a-…`

## Multi-category live SERP smoke

| Category | Query | candidates | ms |
|---|---|---:|---:|
| motherboard | ASUS TUF Gaming B650M-E WIFI | 1 | ~7.3k |
| cpu | Ryzen 7 5800X3D | 1 | ~3.1k |
| gpu | RTX 5070 | 5 | ~3.4k |
| memory | Kingston Fury DDR5 | 5 | ~3.5k |
| ssd | Samsung 990 PRO | 3 | ~3.2k |

HTTP SERP = 403; Camoufox required (documented).
