# Mercado Livre

## Markets / country

- `store=mercadolivre`, `country=BR`, `currency=BRL`
- Domains: `mercadolivre.com.br`, `produto.mercadolivre.com.br`

## Identifiers

- Catalog PDP: `/p/MLB######` → `product_id` / JSON-LD `sku` / `productID`
- Item listing: `produto.mercadolivre.com.br/MLB-######-…` or
  `pdp_filters=item_id:MLB######` → `metadata.item_id`
- Prefer catalog id as `product_id` when both are present

## Live search (matching)

- `supports_search=True`
- SERP: `https://lista.mercadolivre.com.br/{query}`
- Parser: cards `/p/MLB…` e `produto.mercadolivre.com.br/MLB-…`
- Usado por `POST /match` (ADR 0019 / 0025)

## Offer source

- Prefer JSON-LD `Product.offers` (price, currency, availability)
- Fallback: `.ui-pdp-price [itemprop=price]`
- `original_price` from struck price `aria-label` when greater than `price`
- Installments from `#pricing_price_subtitle` (`Nx` + amount) when present
- Pix is **not** invented (often absent as a distinct total on ML)

## Details source

- Title / brand / description / image from JSON-LD
- Specs heuristically split from JSON-LD `description` (`label: value | …`)
- Identity via `resolve_product_identity`

## Images source

- JSON-LD `image` when `include_images=true`

## Pricing semantics

- `price` = selected offer total from JSON-LD / primary price widget
- Never promote installment amount to `price`
- Related / carousel prices on the page must be ignored (prefer JSON-LD)

## Availability semantics

- JSON-LD `schema.org/InStock` → `available`
- `OutOfStock` → `out_of_stock`
- Missing clear signal with price widget → `available`; else `unavailable`

## Seller / marketplace

- Marketplace; seller from PDP DOM when exposed (often absent in HTML-first)

## Fetch strategy

1. **`curl_cffi` HTTP** with Chrome TLS/HTTP2 impersonation (JA3/JA4-aware)
2. Soft block (Snoopy PoW interstitial, HTTP 200) or missing price → **Camoufox**
3. Proxy only after classified `UPSTREAM_BLOCKED` / `AUTH_REQUIRED` (Proxy Cost Mode)

`prepare_fetch_url` / `canonicalize_url` preservam `pdp_filters=item_id:…` e
removem tracking de ads (`matt_*`, `gclid`, `from`, …).

See ADR 0025. Do **not** treat Snoopy HTML as product (`available=false` / fabricated price).

## Identifiers semantics

| Campo | Significado |
|---|---|
| `product_id` / `catalog_product_id` | ID de catálogo `/p/MLB######` |
| `metadata.item_id` | Anúncio selecionado (`pdp_filters=item_id:MLB######` ou URL `/MLB-…`) |
| variation id | Ainda não exposto de forma estável no JSON-LD público |

## Known blocking

- Bot Manager **Snoopy** PoW (`verifyChallenge`, `#continue-button`, `_bmc`)
- `api.mercadolibre.com` frequentemente 403/401 sem app auth
- Camoufox resolve Snoopy (ADR 0017) antes de parsear PDP

## Important invariants

- HTTP 200 ≠ PDP (Snoopy devolve 200 com title/meta sem oferta)
- Nunca parsear HTML Snoopy como produto
- Fail closed em preço ausente (`MissingPriceError`)

## Known limitations

- Seller / GTIN podem estar ausentes no JSON-LD / DOM público
- Cold IPs quase sempre precisam de browser no primeiro hit (Snoopy)
- Galeria via JSON-LD costuma trazer 1 imagem principal
- Visão VIP e lojas sem `supports_search` aparecem no match como
  `SEARCH_UNSUPPORTED` (ERROR terminal), não como omissão silenciosa

## Tests / fixtures

- `tests/fixtures/mercadolivre/`, `tests/unit/test_mercadolivre.py`,
  `tests/unit/test_mercadolivre_http_first.py`
- Coverage de lojas no match: `tests/unit/test_match_store_coverage.py`

## Local test / live

```bash
pip install -e .
python -m pytest tests/unit/test_mercadolivre.py tests/unit/test_mercadolivre_http_first.py -q

# Docker (rebuild após adicionar curl_cffi)
docker compose -f compose.yaml -f compose.spiders.yaml up --build -d
curl -sS -X POST http://localhost:8000/crawl/offer \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.mercadolivre.com.br/.../p/MLB47363706?pdp_filters=item_id%3AMLB6784630760"}'
```

Validação live (2026-09-19): `/crawl/offer`, `/crawl` (± images) OK;
`POST /match` encontrou KaBuM / Magalu / Nissei / Amazon BR / ML.
