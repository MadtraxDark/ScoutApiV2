# Working log — Product Match motherboard false NO_MATCH

Date: 2026-09-22 (run evidence 2026-09-23 UTC)
Product: `0cb47f6a-298b-441d-9154-e33a37d75cd5`
Title: Placa Mae Asus Tuf Gaming B650M-E WIFI, DDR5, Socket AMD AM5, M-ATX, Chipset AMD B650, TUF-GAMING-B650M-E-WIFI

## Baseline run `34cf2cc1-…`

- completed, 0 MATCH / 9 NO_MATCH / 0 ERROR, ~726s
- Queries: `4711387222041`, `asus`, `asus wifi`, `mae asus tuf gaming b650m wifi ddr5 socket`
- Kabum correct PDP rejected: `variant_color_mismatch:wifi!=preto`

## Classification

| Store | Class | Evidence |
|---|---|---|
| kabum | MATCH_FAILURE | Correct PDP; reject `wifi!=preto` |
| magazineluiza | MATCH_FAILURE | Correct titles; `ram 4!=ddr5` / low title sim |
| amazon_us | MATCH_FAILURE | Correct B650M-E; brand-only + title_sim |
| bestbuy / nissei / terabyte | QUERY_FAILURE | `asus` / `asus wifi` → noise |
| aliexpress / shoppingchina | PREFILTER / QUERY | found>0, evaluated=0 |

## Root causes (proven)

1. WiFi bare variant → `color=wifi` → query `asus wifi` + hard reject vs preto
2. No motherboard series phrase / MPN not extracted
3. Title stopword `e` erased `B650M-E` discriminant
4. `parse_motherboard` glued Socket/AMD/M-ATX into model

## After fix — live run `bfdd0a2c-…`

- completed, **4 MATCH** / 5 NO_MATCH / 1 ERROR (amazon_br PARSE_ERROR), ~760s
- MATCH: kabum, magazineluiza, terabyteshop, amazon_us
- Queries: GTIN → `TUF-GAMING-B650M-E-WIFI` → `asus tuf gaming b650m-e wifi` → relax
- Reasons: `brand_model_exact:asus:b650me~b650me` (title_sim complementary)

## Metrics

| Metric | Before | After |
|---|---|---|
| matches_found | 0 | 4 |
| queries (kabum) | brand/wifi noise | GTIN early-stop |
| total_ms | 726401 | 759658 |

## Files

- `identity.py`, `engine.py`, `extra_parsers.py`
- tests motherboard + CPU X3D
- docs: ADR 0033, contracts.md, product-identity.md
