# Working log — Product Match live regression A+B (final)

Date: 2026-09-23
Architecture: ADR 0038 Search adapters confirmed in use (`resolve_search_adapter`)

## Product A — Samsung Galaxy S25 Ultra `800a4caa-…`

Identity: Samsung / Galaxy S25 Ultra / Titânio Preto / GTIN 8806095830933

Historical listings (7): amazon_br, amazon_us, bestbuy, kabum, magazineluiza, nissei, shoppingchina

### Run 1 `e9154f76-…` (Camoufox circuit degraded)

- completed 284s; matches=4; errors=6 (BROWSER_*); no_matches=7
- MATCH: amazon_br, amazon_us, kabum, shoppingchina
- ERROR (infra): bestbuy, magazineluiza, nissei, aliexpress, terabyteshop, visaovip
- Classification: INFRASTRUCTURE_ERROR — not Search/PDP split regression
- Listings preserved in DB

### Run 2 `38c1f584-…` (healthy Camoufox)

- completed 836s; matches=7; errors=1; no_matches=4
- MATCH all historical: amazon_br, amazon_us, bestbuy, kabum, magazineluiza, nissei, shoppingchina
- ERROR visaovip UPSTREAM_BLOCKED (SERP; phone not expected store focus)
- NO_MATCH: pichau, terabyteshop, aliexpress (expected for smartphone)
- Existing listings reused/touched; no duplicate store product IDs

## Product B — ASUS B650M-E WIFI `0cb47f6a-…`

Identity: Asus / TUF Gaming B650M-E… / WiFi / GTIN 4711387222041

Historical listings (6): amazon_us, kabum, magazineluiza, pichau, terabyteshop, visaovip

### Run `9adf92ac-…`

- Mid-run operator restart → lease reclaim (attempts=2); completed 667s wall incl. wait
- matches=6; errors=0; no_matches=4
- MATCH historical + NEW amazon_br: kabum, pichau, magazineluiza, terabyteshop, amazon_us, amazon_br, visaovip
- Visão VIP SearchAdapter: search_ms≈5829, pdp_ms≈53380, prefer_browser path OK
- NO_MATCH: shoppingchina, nissei, bestbuy, aliexpress (expected)

## Architecture

- No spider Search path in StoreSearchService
- eligible = 11 stores (ML/Shopee disabled)
- Search → PDP contract validated (visaovip B650M `/41749/`)

## Code changes

None — no architectural regression requiring fix.

## Unit tests

`test_search_pdp_boundaries` + store_search + visaovip + contracts: 63 passed
