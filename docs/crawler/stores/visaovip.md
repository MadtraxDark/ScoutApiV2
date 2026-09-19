# Visão VIP

## Markets / country

- `store=visaovip`, `country=PY`, `currency=USD`
- Domains: `visaovip.com`, `www.visaovip.com`
- Ciudad del Este storefront; prices advertised as `U$` (USD)
- UI locales: `pt-BR` (default) and `es`

## Identifiers

- `product_id` = `productCode` from the RSC flight payload (UI label **Código**)
- URL shape: `/prod/{category}/{slug}/{productCode}/`
- `sku` = specification **REFERÊNCIA** (manufacturer part / MPN) when present;
  otherwise falls back to `productCode`
- GTIN/EAN only when present in specs or product fields (often absent)

## Offer source

- Next.js App Router RSC flight: `self.__next_f.push([1, "..."])` embeds the
  product object (`productCode`, prices, balance, gallery, specs)
- Open Graph support: `product:price:amount` / `product:price:currency=USD`,
  `og:availability`
- No `__NEXT_DATA__`, no JSON-LD Product, no public product API used

## Details source

- Same flight product object
- Specs from `productSpecifications[]`
  (`specificationName` / `specificationValue`)
- Brand from `manufactureName` (+ specs `MARCA`)
- Model from specs `MODELO`
- Description from `productComents` / `productDescription`
- Attribute gaps filled via global `resolve_product_identity` (title fallback)

## Images source

- When `include_images=true`: `productFrontImage` first, then
  `productGalleryImages` (CDN `cdn.visaovip.com/img/prod/...`)
- Absolute URLs, de-duplicated; excludes brand logos (`/img/marca/`)

## Pricing semantics

- No promotion (`productPromotionPrice` is `0` / falsy):
  - `price` = `productPrice`
  - `original_price` = null
- Promotion (`isProductPromotion` and `productPromotionPrice` > 0):
  - `price` = `productPromotionPrice` (highlighted card price)
  - `original_price` = `productPrice` (strikethrough) when greater than promo
- `pix_price` / installments: **not exposed** in the structured payload → null
- Discount percentage derived only when both current and original exist

## Availability semantics

- Prefer `isProductWithBalance` (`true` → available, `false` → out_of_stock)
- Fallback: `og:availability` (`instock` / `outofstock`)
- Missing signal → `unavailable` (never invent OOS from HTTP 200)
- Soft-404 shell (title `Produto - Visãovip` without product payload) →
  `ParseError`, not `available=false`
- `shipping_to_brazil: false` in offer metadata — PY stock ≠ BR shipping

## Seller / marketplace

- Direct storefront (not marketplace)
- `seller` from `og:site_name` (typically `Visaovip`), else `Visãovip`

## Fetch strategy

- Default Camoufox + Proxy Cost Mode (`FALLBACK`)
- Initial HTML already carries the RSC product payload; no store-specific
  fetch layer. Plain HTTP with a normal UA also returns the flight data.

## Known blocking

- Some non-PDP routes (e.g. naive `/busca`) may 403 without browser context
- Standard WAF/challenge classification via fetcher when it occurs

## Important invariants

- `country=PY` + `currency=USD` (do not convert FX in the spider)
- Do not treat soft-404 / incomplete flight as out of stock
- Do not invent Pix or installment values

## Known limitations

- No live search adapter yet (`supports_search=False`)
- Wrong/missing category slug in the URL can soft-404 even with a valid code
- GTIN often absent

## Tests / fixtures

- `tests/fixtures/visaovip/`, `tests/unit/test_visaovip.py`
