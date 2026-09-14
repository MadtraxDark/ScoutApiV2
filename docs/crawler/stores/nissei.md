# Nissei

## Markets / country

- `store=nissei`, `country=PY`, `currency=PYG`
- Domain: `nissei.com`

## Identifiers

- Prefer Magento / JSON-LD SKU
- If missing: fall back to **canonical URL** as `product_id` / `sku`

## Offer source

- Magento product info + JSON-LD; price from product main block / structured data

## Details source

- Product info main + specs tables / JSON-LD

## Images source

- Gallery when requested; Magento cache URL variants collapsed to catalog path

## Pricing semantics

- PYG amounts; installments only from **explicitly rendered** page JS amounts
- No invented installment schedules

## Availability semantics

- Ambiguous availability defaults to **`available`** (not `unavailable`)
- Clear OOS markers → `out_of_stock`

## Seller / marketplace

- Storefront-style (Nissei)

## Fetch strategy

- Cloudflare-sensitive; warm-up / locale `es-PY` (ADR 0010)
- Proxy Cost Mode `FALLBACK`

## Known blocking

- Cloudflare challenge / hard-block via fetcher

## Important invariants

- Do not fabricate installment math
- Identity fallback to canonical URL is intentional when SKU missing

## Known limitations

- WAF friction; parser depends on Magento markup stability

## Tests / fixtures

- Covered in spider parsing / Nissei unit cases under `tests/unit/`
