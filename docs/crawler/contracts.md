# Crawler contracts

Canonical behavioral contracts for the price crawler. Architecture decisions with
trade-offs live in ADRs (`docs/adr/0008`–`0019`). Store playbooks live under
`docs/crawler/stores/`.

## Pipeline

```
Fetch (Camoufox / urllib / curl_cffi@ML) → Store Adapter (spider) → Offer | Details | Images → Services
```

- Spiders are **parse-only**. They do not own network I/O.
- Fetch / Camoufox / proxy / retries are immutable without an explicit request
  (exceptions: Proxy Cost Mode; **challenge/CAPTCHA resolution**; **auth wall
  bypass**; Mercado Livre TLS-impersonated HTTP-first — ADR 0025). See
  ADR 0009/0010/0014/0016/0017/0018/0025 and
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
| Match (identity) | `MatchResponse` | `ProductMatchService.match_from_item` | same pipeline from a synthetic identity item (no reference URL scrape) |
| Refresh | `OfferRefreshResponse` | `POST /offers/refresh` | re-scrape + offer history diff |

ADR: [0011](../adr/0011-offer-vs-product-details.md), [0012](../adr/0012-optional-image-extraction.md),
[0019](../adr/0019-product-matching.md),
[0024](../adr/0024-product-match-evidence-cascade.md),
[0026](../adr/0026-product-identity-brand-model-variant.md).

### Product Matching (ADR 0019 / 0024)

- Discovery: live SERP on all implemented stores with `supports_search`
  (`kabum`, `bestbuy`, `nissei`, `shoppingchina`, `amazon_br`, `amazon_us`,
  `magazineluiza`, `mercadolivre`, `shopee`, `aliexpress` — ordered by typical GTIN/EAN exposure) via
  `build_search_url` / `parse_search_results`.
  Lojas implementadas sem search (ex. `visaovip`) entram no `/match` como
  `SEARCH_UNSUPPORTED` (ERROR terminal), nunca omitidas.
  Discovery may start from a **URL scrape** (`POST /match`) or from an
  **identity-only** reference (`match_from_item` / `identity_reference_item`)
  — brand/model(/variant) without known store URLs, product IDs, or prices
  fed into Search. Search and Match remain separate stages.
- Scoring cascade (precision-first): variant / **critical identity** blockers →
  accessory / **bundle** (kit+watch/AirPods) reject → **condition**
  (renewed/usado vs novo) → same store+`product_id`
  → validated **GTIN** → normalized **MPN** → brand+model (série comercial / MPN
  cruzado no título) → title similarity (cap; never alone for `auto_match`).
  Critical blockers include GPU suffix (`Ti`/`Super`), phone trim (`Pro`/`Max` /
  `16e`≠`16`), SSD series (`990 evo plus` ≠ `870 evo`), DDR4≠DDR5, and storage
  ≥128GB divergente. Soft model compatibility strips marketing/CPU suffixes and
  treats `Slim 3`≡`Slim 3i` (still rejects Intel↔AMD, chassis codes, CPU SKU
  conflicts, and critical suffixes like `pro`/`plus`/`ti`). Soft model matches
  also require title similarity ≥ 0.75.   Title normalization compacta
  `128 GB`≡`128gb`, preserva MPN como token único e mapeia cores PT/EN/ES
  (`Preto`≡`Black`, `Verde-acinzentado`≡`teal`). Variant key aliases
  (`cor`/`colour`→`color`, `armazenamento` / `tamanho`≥128GB→`storage`) keep the
  color/storage gates active across locales. Opaque store SKUs / MPNs cedem a
  nomes de família inferidos do título (iPhone, IdeaPad, séries SSD/GPU). When
  metadata maps RAM into `storage`, identity prefers SSD-sized capacities from
  the title. Placeholder brands (`outros`, Amazon Renewed store) are ignored so
  title brand can win. GPU **edition** (Dual / Shadow 3X / Gaming Trio) is a
  variant key: missing on one side is unknown, not a conflict; Dual ≠ Gaming
  Trio still rejects (ADR 0026). **Form factor:** discrete GPU / graphics card
  listings must not auto-match notebooks/laptops that merely embed the same
  chip (`form_factor_reject`). Decisions: `auto_match` | `review` | `reject`.
- **Search queries:** `GTIN → display MPN (hyphenated) → brand + spaced series
  + storage → color synonyms (preto/black) → progressive drop → compacted MPN
  → título`. Compact tokens like `990evoplus` / `mzv9s1t0bam` are weak on Amazon
  SERP; `StoreSearchService` also re-ranks cards by query/title/**path** overlap
  (ignora `keywords=` na query-string da Amazon) before the scrape cap.
- **Trusted GTIN learning:** when an `auto_match` yields a check-digit-valid
  GTIN (and brands agree; no cross-match conflicts), the API records it on the
  canonical product (`ProductIdentifier`) and returns `discovered_gtin` /
  `gtin_source`. Mid-match, remaining store searches switch to GTIN-first.
  `review`-only hits never promote a GTIN.
- **Search order:** live match prefers stores that typically expose GTIN/EAN/UPC
  on the PDP (`kabum`, `bestbuy`, `nissei`, `shoppingchina`, then Amazons,
  then `magazineluiza` / `mercadolivre` / `shopee` / `aliexpress`). If the reference listing has no barcode,
  the reference store itself is deprioritized so a GTIN-rich peer can seed
  queries first (`store_search_order.py`).
- **Match cost controls:** per store, stop candidate scrapes after the first
  `auto_match`; cheap-reject SERP titles (accessory/bundle/form-factor/critical
  identity/brand) before PDP scrape; cap consecutive empty non-identifier
  searches (`_MAX_EMPTY_SEARCH_QUERIES`). Structured timing logs:
  `match_store_timing` / `match_total_timing`. Default `include_images=false`.
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
   Never parse a login page as a product. `AUTH_REQUIRED` (falta de login) or
   `UPSTREAM_BLOCKED` only after resolution attempts are exhausted.
4. **Block/challenge/login HTML ≠ `available=false`.** Never invent OOS from a
   robot-check or auth wall page.
5. **Price and availability belong to the same selected variant/offer.**
6. **Images only when requested**; never process gallery over paid proxy
   (Proxy Cost Mode).
7. **Attribute priority:** specifications → structured fields → conservative
   title fallback → `null`. Ambiguous title inference returns `null`.
   **Identity (`brand` / `model` / `variant`):** see below. Structured values
   that already look like a **base model** are only canonicalized — never
   replaced by a weaker title chip (`RTX 5070 Ti` structured wins over
   `RTX 5070` in the title). Cooler lines / opaque MPNs in the store's
   `modelo` field are reclassified to `variant` (or kept as MPN) only when
   a category parser extracts a real base model from the title.
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
| `RequestError(AUTH_REQUIRED)` | Login/session gate (falta de login) after resolution attempts; Shopee `/verify/traffic` or `/buyer/login` | 401 | **Yes** (FALLBACK stores) |
| `RequestError(UPSTREAM_BLOCKED)` | Challenge/CAPTCHA/hard block **after** resolution attempts failed; also Camoufox navigation resets (`NS_ERROR_NET_RESET` / connection refused) treated as upstream block | 502/403-class | **Yes** (FALLBACK stores) |
| `RequestError(UNSUPPORTED_STORE)` | No spider for hostname | — | No |
| `ProductUnavailable` | Reserved domain product state | — | No |

Proxy only after classified `UPSTREAM_BLOCKED` or `AUTH_REQUIRED`. Never fall
back on parse errors.
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

## Brand / model / variant identity (ADR 0026 / 0027)

`model` is the **searchable base identity**. `variant` is an optional commercial
refinement. Category-specific contracts live in `CategoryProfile` registry
(`docs/crawler/product-identity.md`, ADR 0027).

This split is what lets Product Search query `brand=Asus&model=GeForce RTX 5070`
and return Dual / Prime / TUF implementations, then restrict only when
`variant` is sent.

| Field | Meaning | GPU example | Phone example | CPU example |
|---|---|---|---|---|
| `brand` | Manufacturer / board partner | ASUS | Apple | AMD |
| `model` | Base identity that exists in multiple implementations | `GeForce RTX 5070` (not Dual; `Ti`/`Super` stay here) | `iPhone 16 Pro` | `Ryzen 7 7800X3D` |
| `variant` | Optional refinement | `Dual OC Edition` | `color: Black; storage: 256 GB` | `null` unless a clear commercial trim exists |

**Priority:** specifications → structured fields → category-aware title parser →
`null`. Title is fallback. Ambiguous leftover tokens are **not** dumped into
`variant` (`OC Edition` alone → `null`). Manufacturer PNs
(`DUAL-RTX5070-O12G`) are extra evidence, not automatic edition aliases.

**Canonical model:** `Geforce RTX5070` / `NVIDIA GeForce RTX 5070` → display
`GeForce RTX 5070`, comparison key `rtx5070`. `rtx5070` ≠ `rtx5070ti`.

- **Category parsers** (extensible registry, not SKU hardcode): GPU, smartphone,
  CPU, RAM, SSD. GPU board-partner brands use a manufacturer gazetteer
  (ASUS/MSI/Gigabyte/Palit/…), not product SKUs. Notebook GPUs stay in
  `gpu_model`, not product `model`.

**Product Search** (`GET /products/search`): `brand`, `model`, `variant`,
`category` and hot attribute filters (`vram`, `memory_type`, `capacity`, …)
are optional (at least one required). Omitting `variant` returns every
implementation of that base model.

**Product Match:** missing `variant`/`edition` is unknown, not a conflict.
Explicit Dual ≠ Gaming Trio still rejects (ADR 0024).

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
