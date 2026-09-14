# Crawler contracts

Canonical behavioral contracts for the price crawler. Architecture decisions with
trade-offs live in ADRs (`docs/adr/0008`–`0019`). Store playbooks live under
`docs/crawler/stores/`.

## Pipeline

```
Fetch (Camoufox / urllib) → Store Adapter (spider) → Offer | Details | Images → Services
```

- Spiders are **parse-only**. They do not own network I/O.
- Fetch / Camoufox / proxy / retries are immutable without an explicit request
  (exceptions: Proxy Cost Mode; **challenge/CAPTCHA resolution**; **auth wall
  bypass**). See ADR 0009/0010/0014/0017/0018 and
  `.cursor/rules/scraper-camoufox-immutable.mdc`,
  `.cursor/rules/captcha-challenge-resolution.mdc`,
  `.cursor/rules/auth-wall-resolution.mdc`.

## Models and endpoints

| Surface | Model | Endpoint | Extracts |
|---|---|---|---|
| Offer | `ProductOffer` | `POST /crawl/offer` | `extract_offer` only |
| Full | `ProductPriceItem` | `POST /crawl` | offer + details (+ images if asked) |
| Details | `ProductDetails` | (composed into full) | `extract_details` (no gallery) |
| Images | `list[str]` | via `include_images=true` | `extract_images` only when requested |
| Match | `MatchResponse` | `POST /match` | live search + scrape + `MatchingEngine` |
| Refresh | `OfferRefreshResponse` | `POST /offers/refresh` | re-scrape + offer history diff |

ADR: [0011](../adr/0011-offer-vs-product-details.md), [0012](../adr/0012-optional-image-extraction.md),
[0019](../adr/0019-product-matching.md).

### Product Matching (ADR 0019)

- Discovery: live SERP on all implemented stores with `supports_search`
  (`kabum`, `bestbuy`, `nissei`, `shoppingchina`, `amazon_br`, `amazon_us`,
  `magazineluiza`, `shopee` — ordered by typical GTIN/EAN exposure) via
  `build_search_url` / `parse_search_results`.
- Scoring: validated GTIN first; brand+model; variant gates (color/storage/size
  /capacity/pack) with canonicalization for storage unit spacing (`256 gb`≡
  `256gb`) and common PT/EN color synonyms (`preto`≡`black`, `luna grey`/
  `arctic grey`/`cinza`≡`grey`); accessory tokens reject; title similarity
  never alone for `auto_match`. Soft model compatibility strips marketing/
  CPU suffixes and treats `Slim 3`≡`Slim 3i` (still rejects Intel↔AMD, distinct
  chassis codes, and conflicting CPU SKUs such as Core 3 100U vs i5-1335U). Soft
  model matches also require title similarity ≥ 0.75. Opaque store SKUs yield to
  title-inferred family names (iPhone / IdeaPad Slim). When metadata maps RAM into
  `storage`, identity prefers SSD-sized capacities from the title. When PDP
  `model` is missing, identity may infer it from the title; placeholder brands
  (`outros`, Amazon Renewed store) are ignored so title brand can win.
  Decisions: `auto_match` | `review` | `reject`.
- **Trusted GTIN learning:** when an `auto_match` yields a check-digit-valid
  GTIN (and brands agree; no cross-match conflicts), the API records it on the
  canonical product (`ProductIdentifier`) and returns `discovered_gtin` /
  `gtin_source`. Mid-match, remaining store searches switch to GTIN-first.
  `review`-only hits never promote a GTIN.
- **Search order:** live match prefers stores that typically expose GTIN/EAN/UPC
  on the PDP (`kabum`, `bestbuy`, `nissei`, `shoppingchina`, then Amazons,
  then `magazineluiza` / `shopee`). If the reference listing has no barcode,
  the reference store itself is deprioritized so a GTIN-rich peer can seed
  queries first (`store_search_order.py`).
- Persistence (PostgreSQL): `CanonicalProduct`, `StoreListing`, `OfferSnapshot`,
  `OfferEvent` — refresh **appends** snapshots/events (never silent overwrite).
- `UPSTREAM_BLOCKED` on refresh → `scrape_failed` (listing stays active).
  Unparseable/gone PDP → `offer_removed`.

## Critical invariants

1. **HTTP 200 ≠ available.** Parse availability from product signals.
2. **Challenge/CAPTCHA must be resolved** (ADR 0017 — critical/immutable). Do
   not treat detection alone as a successful terminal policy. Never parse a
   challenge page as a product (`available=false` / fabricated price). Emit
   `RequestError(code="UPSTREAM_BLOCKED")` only after resolution attempts are
   exhausted.
3. **Auth wall / login-gate bypass is mandatory** (ADR 0018 — critical/immutable).
   Login, soft-auth, or session gates that block public offers must be resolved
   or bypassed (operator-owned session/credentials via env — never in Git).
   Never parse a login page as a product. `UPSTREAM_BLOCKED` only after
   resolution attempts are exhausted.
4. **Block/challenge/login HTML ≠ `available=false`.** Never invent OOS from a
   robot-check or auth wall page.
5. **Price and availability belong to the same selected variant/offer.**
6. **Images only when requested**; never process gallery over paid proxy
   (Proxy Cost Mode).
7. **Attribute priority:** specifications → structured fields → conservative
   title fallback → `null`. Ambiguous title inference returns `null`.
8. **Identifiers** (GTIN/EAN/UPC/SKU/`product_id`) are **never** inferred from
   arbitrary title numbers (`utils/product_attributes.py`).
9. **Foreign stores as price reference:** stock ≠ shipping to Brazil
   (Best Buy ADR 0013; Amazon US ADR 0015; Shopping China store doc).
10. **No FX conversion inside spiders.** Keep marketplace currency as advertised.
11. **Conditional pricing** (Pix, coupon, Prime, Subscribe & Save, installments)
    must preserve conditions — never promote monthly payment or coupon value to
    `price`.
12. **Fail closed on essential parse gaps.** Missing identity/price →
    `ParseError` / `MissingPriceError`; do not emit fabricated prices (ADR 0008).
13. **Secrets/cookies/tokens** are never versioned or written into docs.

## Errors

| Exception | Meaning | Typical HTTP | Proxy fallback? |
|---|---|---|---|
| `ParseError` / `MissingPriceError` | Page shape / price not understood | 422 | **No** |
| `RequestError(UPSTREAM_BLOCKED)` | Challenge/CAPTCHA/auth wall/hard block **after** resolution attempts failed; or unresolved traffic verify | 502/403-class | **Yes** (FALLBACK stores) |
| `RequestError(UNSUPPORTED_STORE)` | No spider for hostname | — | No |
| `ProductUnavailable` | Reserved domain product state | — | No |

Proxy only after classified `UPSTREAM_BLOCKED`. Never fall back on parse errors.
Canonical: ADR 0014 + `.cursor/rules/proxy-cost-mode.mdc`.
Challenge resolution: ADR 0017 + `.cursor/rules/captcha-challenge-resolution.mdc`.
Auth wall bypass: ADR 0018 + `.cursor/rules/auth-wall-resolution.mdc`.

## Pricing fields

| Field | Use |
|---|---|
| `price` | Current Buy Box / primary offer total (not installment, not coupon amount) |
| `original_price` | Struck / list price when strictly greater than `price` |
| `pix_price` | Explicit Pix total when the store exposes it (BR); never invent |
| `installment_price` / `installment_count` | Explicit installment schedule; never treat as `price` |
| `currency` | Marketplace currency of the scraped page |
| `metadata.pricing` | Conditions (coupon, Prime badge, subscribe, pix_available, …) |

## Availability

`Availability = "available" | "out_of_stock" | "unavailable"`.

- `available` / `out_of_stock` refer to the **selected offer in that marketplace**.
- Shipping restrictions to Brazil on foreign sites must **not** force OOS.
- Put logistics notes in metadata (e.g. `shipping_to_brazil: false`).

## Variants

- Resolve the **selected** variant/model (URL param, twister ASIN, `display_model_id`, …).
- Never mix price/seller/images from different variants.
- Prefer the store’s selected/default sellable unit — **not** “cheapest across models”
  unless the store UI itself presents that as the selected offer.

## Source tracking

Prefer `metadata["source"]` maps (field → provenance tag) so regressions show
where a value came from (`product-state`, `json-ld`, `buybox-price`, …).

## Adding a store

1. `StoreConfig` in `stores.py` (domains, country, currency, proxy policy).
2. Spider under `spiders/<region>/` with `extract_offer` / `extract_details` /
   optional `extract_images`.
3. Fixtures + unit tests under `tests/fixtures/<store>/` and `tests/unit/`.
4. Store playbook under `docs/crawler/stores/<store>.md`.
5. ADR only if the store introduces a durable architectural trade-off.
