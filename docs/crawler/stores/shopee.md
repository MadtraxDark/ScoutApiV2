# Shopee BR

## Markets / country

- `store=shopee`, `country=BR`, `currency=BRL`
- `supports_images=True` (URLs from already-fetched PDP payload)
- `image_fetch_cost=high` → PriceScout checkbox default **off**
- Domain: `shopee.com.br`

## Identifiers

- `product_id` = `item_id`
- `sku` = selected `model_id` when present

## Live search (matching)

- `supports_search=True`
- SERP: `https://shopee.com.br/search?keyword={query}`
- Camoufox intercepts `/api/v4/search/search_items` (same Mode A as PDP
  `get_pc` — signatures minted by Shopee JS, never forged)
- Parser preference: captured search JSON → `-i.{shop_id}.{item_id}` links →
  embedded ids in page scripts
- **Known limitation:** cold/anonymous SERP often hits `verify/traffic` before
  `search_items` fires. Mitigation: seeded Camoufox profile
  (`make seed-shopee` / `make seed-shopee-login`) + `ProxyPolicy.FALLBACK`.
  Without a warm session, search may still return `AUTH_REQUIRED` (falta de
  login) — never fabricate matches from the block page. On `/verify/traffic`,
  the fetcher **attempts auth bypass** (navigate to `/buyer/login` + operator
  credentials) before emitting `AUTH_REQUIRED`, then falls back to proxy when
  `ProxyPolicy.FALLBACK` applies.
- Anti-bot/SERP fragility is higher than BR retail SERPs; failures surface as
  empty candidates / `AUTH_REQUIRED` / `UPSTREAM_BLOCKED`, never as fabricated
  matches
- Used by `POST /match` (ADR 0019)

## Offer source

- Prefer captured PDP JSON (`get_pc` / embedded item payload)
- Prices often in **micros** (divide by `100000` unless already decimal-scale)

## Timed promotion

- Flash / Oferta Relâmpago: bloco `flash_sale` / `deep_discount` com
  `end_time` (unix) no payload ou na model selecionada
- Spider anexa `metadata.promotion` (`type=flash_sale`) via
  `shopee_flash_promotion` quando o fim absoluto existe
- Fixtures sem flash → oferta normal sem campo `promotion`

## Details source

- Same PDP payload: title, brand, specs, selected model attributes
- Base chip/model via `resolve_product_identity` (ADR 0026); selected Shopee
  model label still wins as public `variant` when present

## Images source

- Gallery URLs from PDP payload (`product_images` / selected model) when
  `include_images=true` and egress is **not** paid proxy
- Preview returns URLs only — no CDN binary download in crawl
- Shopee image CDN (`down-br.img.susercontent.com`) is typically public; paid
  proxy remains for protected PDP fetch, not for later Drive ingest of approved
  URLs
- When proxy was used for the PDP: `images_omitted: proxy-cost-mode`
- Default checkbox off (`image_fetch_cost=high`) because the PDP path itself is
  browser-heavy

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
  classified `UPSTREAM_BLOCKED` / `AUTH_REQUIRED` (e.g. `/verify/traffic`)
- Gallery never via paid proxy; `exclude_addons=[UBO]` (Camoufox #345)

## Known blocking behavior

Classify **after** fetch-layer resolution attempts fail:

- `/verify/traffic` → `RequestError(code="AUTH_REQUIRED")` — retorno claro de
  **falta de login/sessão** (HTTP 401). Mensagem aponta
  `SHOPEE_AUTH_EMAIL` / `SHOPEE_AUTH_PASSWORD` ou `make seed-shopee-login`.
  Continua elegível a proxy FALLBACK.
- login redirect with `next=` / `/buyer/login` → `AUTH_REQUIRED` — **must
  attempt auth bypass** first (ADR 0018): seeded profile
  (`make seed-shopee-login`) and/or `SHOPEE_AUTH_EMAIL` / `SHOPEE_AUTH_PASSWORD`
  (operator env only)
- anti-bot error `90309999` → `UPSTREAM_BLOCKED`
- CAPTCHA / unusual-traffic markers without PDP JSON → `UPSTREAM_BLOCKED`
  (ou `AUTH_REQUIRED` se a página for auth wall)

Other PDP `error` values → `ParseError` (not proxy fallback).

## Proxy-elimination research (2026-09-14)

Goal: remove or replace paid proxy dependency for Shopee BR.

| Approach | Result | Notes |
|---|---|---|
| Current `FALLBACK` (direct → proxy) | **Stable** | Live: direct `blocked` (`verify/traffic`, no `get_pc`); proxy `success` + `get_pc` intercept (2/2 PDPs) |
| Plain HTTP `get_pc` (+ Referer / X-API-SOURCE) | Fail | HTTP **403**; community: needs per-request SDK signatures |
| Camoufox direct only (seeded profile, UBO off) | Fail | `AUTH_REQUIRED` `/verify/traffic` |
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
  (`SHOPEE_AUTH_EMAIL` / `SHOPEE_AUTH_PASSWORD` or `make seed-shopee-login`).
  Headless login may still leave `/verify/traffic` uncleared — fetcher then
  emits `AUTH_REQUIRED` and FALLBACK retries with proxy (one auth attempt per
  settle; no multi-minute login loop).
- After auth/proxy, SERP can still return **zero** candidates (session/geo).
  `/match` stops after two consecutive empty searches for that store (does not
  burn the full query list × multi-minute browser sessions).
- Image extraction disabled by store policy
- No stable open-source path that removes proxy **and** skips a real browser
  for `get_pc`

## Tests / fixtures

- `tests/fixtures/shopee/`, `tests/unit/test_shopee.py`, proxy cost tests
- Live cost/proxy probes: `scripts/measure_shopee_fetch_cost.py`