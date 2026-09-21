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
- Parser: prioriza `a.poly-component__title` / `a.ui-search-link` com
  título; ignora carrosséis `#intervention_type=` (Norton/M365 etc.)
- Usado por `POST /match` (ADR 0019 / 0025)
- Soft-block na lista pode ser:
  1. **Snoopy PoW** (HTTP 200 fino com `snoopy-script`) — **resolver** com
     Camoufox (ADR 0017); validado live 2026-09-21 (direct, sem proxy)
  2. **`gz/account-verification`** — bypass **sem** `MERCADOLIVRE_AUTH_*`:
     Snoopy/Continuar → warm `www.mercadolivre.com.br` → reopen `go`/resume
     (ADR 0018). Profile persistente Camoufox opcional
     (`make seed-mercadolivre`). Se esgotar → `AUTH_REQUIRED` + proxy
     FALLBACK (nunca SERP vazia / `NO_MATCH`)
- HTTP-first (`curl_cffi`): SERP `ui-search` OK; Snoopy/auth wall → Camoufox
  (+ proxy FALLBACK só após bloqueio classificado)

Validação live (2026-09-21): identity-only `Gigabyte RTX 5060` → SERP com
candidatos Gigabyte `/p/MLB…` → `auto_match` (`MLB50869989` Eagle OC) sem
URL pré-fornecida. Report:
`data/live-match-reports/ml_rtx5060_retest_20260921T190550Z.json`.

## Offer source

- Prefer JSON-LD `Product.offers` (price, currency, availability)
- Fallback: `.ui-pdp-price [itemprop=price]`
- `original_price` from struck price `aria-label` when greater than `price`
- Installments from `#pricing_price_subtitle` (`Nx` + amount) when present
- Pix is **not** invented (often absent as a distinct total on ML)

## Timed promotion

- Oferta Relâmpago: `lightning_deal_configuration.finish_date` embutido no
  HTML/JSON do PDP (às vezes sob chave `MLB…` / `MLBU…`)
- Spider anexa `metadata.promotion` (`type=lightning_deal`) via
  `mercadolivre_lightning_promotion` quando o campo existe
- Sem o bloco → sem `metadata.promotion` (sem inventar timer)
- Seller Promotions API exige token de vendedor — **fora** do path público

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

See ADR 0025. Snoopy deve ser **resolvido** (Camoufox / ADR 0017); HTML de
challenge nunca vira produto (`available=false` / preço fabricado).
`UPSTREAM_BLOCKED` só após esgotar resolução.

## Identifiers semantics

| Campo | Significado |
|---|---|
| `product_id` / `catalog_product_id` | ID de catálogo `/p/MLB######` |
| `metadata.item_id` | Anúncio selecionado (`pdp_filters=item_id:MLB######` ou URL `/MLB-…`) |
| variation id | Ainda não exposto de forma estável no JSON-LD público |

## Known blocking

- Bot Manager **Snoopy** PoW (`verifyChallenge`, `#continue-button`, `_bmc`) —
  comum na SERP lista via HTTP; Camoufox resolve (ADR 0017)
- SERP/lista: às vezes `gz/account-verification` — bypass credential-free
  (warm + resume + Snoopy); `AUTH_REQUIRED` só após esgotar; proxy FALLBACK
  elegível (ADR 0018). **Não** há dependência de `MERCADOLIVRE_AUTH_*`
- `api.mercadolibre.com` frequentemente 403/401 sem app auth
- Camoufox resolve Snoopy (ADR 0017) antes de parsear PDP/SERP

## Important invariants

- HTTP 200 ≠ PDP (Snoopy devolve 200 com title/meta sem oferta)
- Challenge Snoopy **deve ser resolvido** (Camoufox + ADR 0017); auth wall
  **deve** usar bypass de sessão (warm/resume/Snoopy — ADR 0018), sem
  exigir env de senha ML. Proibir bypass é inválido
- HTML Snoopy ≠ produto: emitir `UPSTREAM_BLOCKED` para o fetch continuar
  resolução — nunca fabricar `available=false` / preço / promo
- Fail closed em preço ausente **após** PDP real (`MissingPriceError`)

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
