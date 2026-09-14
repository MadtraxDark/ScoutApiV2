# Best Buy

## Markets / country

- `store=bestbuy`, `country=US`, `currency=USD`
- Domain: `bestbuy.com`
- Used as **US list-price reference** for BR comparison

## Identifiers

- Product id / SKU from product JSON / page state
- GTIN/UPC when present

## Offer source

- Product JSON + semantic markup / JSON-LD
- Modern `/product/{slug}/{bsin}` PDPs: Apollo SSR (`ApolloSSRDataTransport`)
  may embed `price.customerPrice` / `skuId` / `bsin` in non-JSON script pushes —
  spider extracts those fields when bare JSON product state is absent

## Details source

- Same product state; specs and model fields

## Images source

- Gallery when `include_images=true`

## Variant model

- Dimension map → `key: value; ...`
- **US carriers** (AT&T, Verizon, T-Mobile, …) are commercial conditions, not
  product identity — exclude from normalized `variant`; keep in metadata
  (`carrier`, `carrier_locked`)

## Pricing semantics

- `price` / `original_price` / discount from offer state
- Carrier-locked financing is **not** product installment — omit installment
  when `carrier_locked`

## Availability semantics

Canonical: [ADR 0013](../../adr/0013-bestbuy-availability-semantics.md).

- Price-first for active US offers
- Clear sold-out / discontinued → `out_of_stock`
- Missing shipping to Brazil / ZIP / store-pickup-only does **not** mean OOS
- `location_dependent` may be flagged in metadata without flipping availability

## Seller / marketplace

- Merchant from offer state; default display `"Best Buy"` when absent

## Fetch strategy

- `prepare_fetch_url` appends `intl=nosplash` to skip international splash
  (fetch-only; stripped from `canonical_url`)
- Accepts modern `/product/{slug}/{bsin}` and legacy
  `/site/{slug}/{sku}.p?skuId={sku}` (Best Buy 301-redirects legacy → product)
- Bare `/site/{sku}.p` gets `skuId` injected for the fetch
- If a legacy `skuId` lands on a different SKU after redirect → `ParseError`
  (fail-closed redirect leak)
- Camoufox + Proxy Cost Mode

## Known blocking

- Cloudflare/WAF via fetcher classification

## Important invariants

- US stock ≠ BR shipping eligibility
- No FX conversion in spider
- `canonical_url` must not keep `intl=nosplash`

## Known limitations

- Location/ZIP can change page copy without changing stock semantics
- Deactivated legacy SKUs may 404 (`page not found`) or redirect elsewhere —
  mismatch is rejected; true 404 stays `ParseError`

## Tests / fixtures

- `tests/fixtures/bestbuy/` (incl. `product_apollo_ssr.html`),
  `tests/unit/test_bestbuy.py`
