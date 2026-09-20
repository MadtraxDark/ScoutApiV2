# KaBuM

## Markets / country

- `store=kabum`, `country=BR`, `currency=BRL`
- Domain: `kabum.com.br`

## Identifiers

- `product_id` from product state `id`, else JSON-LD / URL `/produto/(\d+)`
- `sku` from product SKU fields when present
- GTIN/EAN from product state (`gtin`/`ean`/`gtin13`) or specs (`código de barras`)
  when present — preferred early target in live match search order
  (`docs/crawler/contracts.md`)

## Live search (matching)

- `supports_search=True`
- SERP: `https://www.kabum.com.br/busca/{query}`
- Parser: product card links `/produto/{id}`
- Used by `POST /match` (ADR 0019)

## Offer source

- Prefer `__NEXT_DATA__` → `props.pageProps.product`
- Fallbacks: JSON-LD offer, price selectors

## Details source

- Specs from `technicalInformation` (often HTML fragments `- label: value`)
- Brand/model via product state + `resolve_product_identity` (ADR 0026:
  cooler/MPN in specs is reclassified when the title has a base chip)

## Images source

- Product gallery from product state when `include_images=true`

## Pricing semantics

- `price` = regular product price
- `pix_price` = `prices.priceWithDiscount` or prime discount field when present
- `original_price` = `oldPrice` when greater than `price`
- Installments from product `installment` state

## Availability semantics

- Explicit product flags first → JSON-LD → body / purchase controls
- Missing clear signal → `unavailable` (not price-first)

## Seller / marketplace

- `sellerName` or marketplace seller on the current listing

## Fetch strategy

- Default Camoufox + Proxy Cost Mode (`FALLBACK`)

## Known blocking

- Standard WAF/challenge via fetcher (`UPSTREAM_BLOCKED`)

## Important invariants

- Pix is an explicit discounted total, not inventado
- Marketplace seller may differ from KaBuM retail

## Known limitations

- Heavily dependent on `__NEXT_DATA__` shape

## Tests / fixtures

- `tests/fixtures/kabum/`, `tests/unit/test_kabum.py`
