# Nissei

## Markets / country

- `store=nissei`, `country=PY`, `currency=PYG` (default spider currency)
- Domain: `nissei.com`
- Locale `/br/` PDPs frequently advertise **USD** (`US$`); currency is detected
  from the page (`USD` / `PYG`) rather than forced from the class default

## Identifiers

- Prefer Magento / JSON-LD SKU
- On **configurable** PDPs, when the selected (or sole-option) child is known via
  Magento swatches + `contentsWithIds`, prefer the **child SKU** /
  `variant_product_id` and keep `parent_product_id` in metadata
- If missing: fall back to **canonical URL** as `product_id` / `sku`

## Live search (matching)

- Search: `matching.search_adapters` (PDP spider sem Search)
- SERP: `https://nissei.com/br/catalogsearch/result/?q={query}`
  (locale prefix is required — bare `/catalogsearch/…` redirects to home;
  `/br/` ranks the BR storefront PDPs used by Product Match; `/py/` also works
  but may demote some S-series results)
- Parser: Magento product item links (slug PDPs and `.html`)
- SERP often returns the **family / parent** title without storage/color —
  that is **not** an early reject; full PDP fetch resolves the selected variant
- Used by `POST /match` (ADR 0019)

## Offer source

- Magento product info + JSON-LD; price from product main block / structured data
- Configurable: prefer `contentsWithIds[].item_price` when the selected child is known

## Details source / selected variant

Priority (generic resolver + Magento state):

1. Selected swatch state (`data-option-selected` / selected option label /
   `aria-checked=true`)
2. **Sole-option** attributes (only one choice — not “first of many”)
3. Specs table (`#product-attribute-specs-table`, labels like `Memoria Interna`,
   `Cor`, `Memoria RAM`)
4. Structured / title fallback
5. URL slug as **supporting evidence only**
6. `null` when no reliable evidence

Magento sources used:

- `.product-info-main .swatch-attribute` (`color`, `memoria_interna`, `memoria_ram`, …)
- Inline `contentsWithIds` map (child product id → SKU / color / price)
- Canonical `<link rel="canonical">` (parent vs child URLs stay distinct)

Conflicts (e.g. slug says 256 GB, selected swatch says 512 GB) keep the selected
variant and record `metadata.variant_conflicts` when useful.

`metadata.source` records per-attribute origins (`selected-variant`,
`product-specifications`, `url-slug-evidence`, …).

## URL semantics

- Parent configurable URL (no capacity/color in slug) and child/simple URLs
  (slug includes capacity/color) can be **distinct listings** with distinct
  canonical URLs and SKUs
- Do **not** dedupe by stripping the slug tail
- URL evidence may fill gaps only after richer page sources

## Images source

- Gallery when requested; Magento cache URL variants collapsed to catalog path

## Pricing semantics

- Amounts as advertised on the page (PYG or USD)
- Installments only from **explicitly rendered** page JS amounts
- No invented installment schedules

## Availability semantics

- Ambiguous availability defaults to **`available`** (not `unavailable`)
- Clear OOS markers → `out_of_stock`

## Seller / marketplace

- Storefront-style (Nissei)

## Fetch strategy

- Cloudflare-sensitive; warm-up / locale `es-PY` (ADR 0010)
- Proxy Cost Mode `FALLBACK`
- Prefer structured Magento HTML/JS already in the SSR payload — no extra
  browser navigation only to read visible swatch text when sole-option /
  `contentsWithIds` already determine the variant

## Known blocking

- Cloudflare challenge / hard-block via fetcher

## Important invariants

- Do not fabricate installment math
- Identity fallback to canonical URL is intentional when SKU missing
- Never pick the first of many unselected Magento options
- Storage/color missing from the URL ≠ missing on the product
- SEARCH may use the family query; MATCH confirms storage/color on the PDP

## Known limitations

- WAF friction; parser depends on Magento markup stability
- Full Magento `jsonConfig` is often **not** embedded in SSR (theme/FPC); child
  resolution uses swatches + `contentsWithIds` instead
- Catalog assortment / Magento relevance varies; capacity-heavy queries may
  rank A-series above S-series — family queries + phone-line SERP rejects
  (Galaxy A ≠ Galaxy S) keep scrape budget for the right PDP
- Some simple PDPs disagree between title/URL and the specs table (e.g. title
  `128 GB` vs specs `Memoria Interna: 256 GB`); specs win and
  `metadata.variant_conflicts` records the inconsistency when URL evidence
  disagrees

- When multiple swatch options exist and none are selected, storage/color stay
  `null` (missing ≠ conflict)

## Tests / fixtures

- `tests/fixtures/nissei/`
- `tests/unit/test_nissei_variants.py`
- Legacy installment case in `tests/unit/test_spider_parsing.py`
