# Shopee BR

## Markets / country

- `store=shopee`, `country=BR`, `currency=BRL`
- Domain: `shopee.com.br`
- `supports_images=False` (store + Proxy Cost Mode)

## Identifiers

- `product_id` = `item_id`
- `sku` = selected `model_id` when present

## Offer source

- Prefer captured PDP JSON (`get_pc` / embedded item payload)
- Prices often in **micros** (divide by `100000` unless already decimal-scale)

## Details source

- Same PDP payload: title, brand, specs, selected model attributes

## Images source

- Omitted by policy (`supports_images=False`); do not enable gallery over proxy

## Variant model

- Prefer URL `display_model_id` / related params
- If absent: **first sellable model in stable order — never “cheapest wins”**

## Pricing semantics

- Price from selected model
- Pix/coupon breakdown from product price / final-price-info when present
- Coupon-gated Pix stays in metadata conditions

## Availability semantics

- From selected model / item stock signals in PDP JSON

## Seller / marketplace

- Shop name from payload (`shop` / seller fields)

## Fetch strategy

- Minimal fetch: stop after `get_pc` when possible (ADR 0014)
- Camoufox intercepts `/api/v4/pdp/get_pc` (signatures minted by Shopee JS —
  plain HTTP cannot forge `af-ac-enc-dat` / `x-sap-*`)
- Proxy Cost Mode `FALLBACK`: **direct first**, residential proxy only after
  classified `UPSTREAM_BLOCKED` (e.g. `/verify/traffic`)
- Gallery never via paid proxy; `exclude_addons=[UBO]` (Camoufox #345)

## Known blocking behavior

Classify as `UPSTREAM_BLOCKED` (retryable / proxy-eligible) **after** fetch-layer
resolution attempts fail:

- `/verify/traffic`
- login redirect with `next=` / `/buyer/login` — **must attempt auth bypass**
  first (ADR 0018): seeded profile (`make seed-shopee-login`) and/or
  `SHOPEE_AUTH_EMAIL` / `SHOPEE_AUTH_PASSWORD` (operator env only)
- anti-bot error `90309999`
- CAPTCHA / unusual-traffic markers without PDP JSON

Other PDP `error` values → `ParseError` (not proxy fallback).

## Proxy-elimination research (2026-09-14)

Goal: remove or replace paid proxy dependency for Shopee BR.

| Approach | Result | Notes |
|---|---|---|
| Current `FALLBACK` (direct → proxy) | **Stable** | Live: direct `blocked` (`verify/traffic`, no `get_pc`); proxy `success` + `get_pc` intercept (2/2 PDPs) |
| Plain HTTP `get_pc` (+ Referer / X-API-SOURCE) | Fail | HTTP **403**; community: needs per-request SDK signatures |
| Camoufox direct only (seeded profile, UBO off) | Fail | `UPSTREAM_BLOCKED` `/verify/traffic` |
| Direct + disable HTTP/3 prefs | Fail | Still traffic-verify; HTTP/3 prefs help proxy IP-leak, not SGW gate |
| Reverse-engineer `af-ac-enc-dat` / `x-sap-sec` | Discarded | Fragile, high maintenance; OSS (tail-fin / shopee-mcp) uses **browser capture** instead — already our model |
| Paid scraper APIs (Oxylabs / Bright Data / etc.) | Not adopted | Paid vendor; needs explicit operator approval; does not beat in-repo Camoufox+FALLBACK |
| Headed seed + operator login | Complementary | Improves session; does **not** replace BR residential IP when egress is blocked |

**Decision:** keep Camoufox + `get_pc` intercept + `ProxyPolicy.FALLBACK`. Do not force
`REQUIRED` proxy; do not switch to HTTP-only. Re-test direct-only when egress IP /
seeded session changes (`make seed-shopee` / `seed-shopee-login`).

References: Stack Overflow 90309999 signature headers; [bintangtimurlangit/shopee-mcp](https://github.com/bintangtimurlangit/shopee-mcp) (browser intercept); [tail-fin-shopee](https://docs.rs/tail-fin-shopee/) (HTTP cookies insufficient for `get_pc`); Camoufox #345 (uBlock).

## Important invariants

- Selected model drives price, sku, and availability together
- Never pick cheapest model automatically

## Known limitations

- Aggressive anti-bot; on typical Docker egress, **direct often hits**
  `/verify/traffic` and needs BR residential proxy fallback
- Auth walls need seeded Camoufox profile and/or operator credentials
- Image extraction disabled by store policy
- No stable open-source path that removes proxy **and** skips a real browser
  for `get_pc`

## Tests / fixtures

- `tests/fixtures/shopee/`, `tests/unit/test_shopee.py`, proxy cost tests
- Live cost/proxy probes: `scripts/measure_shopee_fetch_cost.py`