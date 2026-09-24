# TerabyteShop PDP investigation — 2026-09-24

## Regression URL

Tracked:
`https://www.terabyteshop.com.br/produto/22809/placa-mae-gigabyte-b650m-aorus-elite-chipset-b650-amd-am5-atx-ddr5?gad_source=1&gad_campaignid=16136003025&gbraid=…&gclid=…`

Clean:
`https://www.terabyteshop.com.br/produto/22809/placa-mae-gigabyte-b650m-aorus-elite-chipset-b650-amd-am5-atx-ddr5`

## Baseline (before)

- Production fetch chain: Kabum → Pichau → ML → Amazon → **Camoufox only** for Terabyte (no HTTP-first).
- API often served **stale L1 memory cache** with partial parse.
- Parser gaps on valid PDP HTML:
  - `sku` = brand string from JSON-LD (`Gigabyte`)
  - `gtin` / `mpn` ignored
  - `specifications={}` despite accordion
  - `pix_price` / installments / original missing
  - images = single JSON-LD `/produto/p/` thumb
  - title kept `| Terabyte` suffix
- Cold Camoufox failure ⇒ user-visible “não trouxe dados” even though `curl_cffi` returns full PDP in ~250 ms.

## Fetch comparison (clean URL)

| Sinal | HTTP curl_cffi | Camoufox (one-shot probe) |
|---|---|---|
| status | 200 | launch fail in probe (`BROWSER_LAUNCH_ERROR`) |
| bytes | ~199 798 | n/a |
| title | product title | n/a |
| Product JSON-LD | sim | n/a |
| price | sim | n/a |
| h1 | sim | n/a |
| specs accordion | sim | n/a |
| images gallery `/g/` | sim | n/a |
| challenge | não (false positive `challenge-platform` string only in GTM; length gate OK) | n/a |
| duration | ~220–280 ms | n/a |

Tracking params: same PDP body; canonicalization already strips `gclid`/`gbraid`/`gad_*`.

## Root cause

1. **FETCH gap** — docs claimed HTTP-first/`curl_cffi`, but `build_html_fetcher` never wrapped Terabyte; every live miss went to Camoufox.
2. **PARSER weakness** — even with valid HTML, details/commercial fields were discarded (`DETAIL_EXTRACTION_FAILURE` + incomplete commercial parse). Classification: combined **FETCH architectural gap** + **PARSER_REGRESSION / DETAIL_EXTRACTION_FAILURE**.

## Sources discovered (live PDP)

- JSON-LD `Product` (name, brand, mpn, gtin13, offers.price, image thumb)
- DOM `#valVista` (à vista/Pix), `#nParc`/`#Parc` installments, `p.precode del` original
- Accordion `div.especificacoes` `<strong>Label:</strong><br>value`
- Gallery `img.terabyteshop.com.br/produto/g/…`
- jQuery countdown `$('#ctd{id}').countdown(...)`
- No Next.js/`__NEXT_DATA__` hydration blob

## Changes

- `TerabyteShopHttpFirstHtmlFetcher` + wire as outermost progressive wrapper
- Rewrite `TerabyteShopSpider` extractors (offer/details/images) + `prepare_fetch_url` canonicalize
- Tests: http_first, spider, search→PDP contract
- Docs: `docs/crawler/stores/terabyteshop.md`

## Multi-category live (curl_cffi + spider)

| Category | product_id | price | specs | images | promo |
|---|---|---:|---:|---:|---|
| motherboard | 22809 | 1199.99 | 27 | 6 | yes |
| cpu | 20782 | 559.99 | 23 | 5 | yes |
| gpu | 40448 | 1249.99 | 30 | 2 | yes |
| ram | 23362 | 1999.90 | 24 | 3 | yes |
| ssd | 42990 | 5999.90 | 21 | 3 | yes |

## After (parser on regression HTML)

| Campo | Antes | Depois | Fonte |
|---|---|---|---|
| product_id | 22809 | 22809 | url |
| sku | Gigabyte | 22809 | url (ignore brand-as-sku) |
| title | … \| Terabyte | Placa-Mãe … DDR5 | json-ld cleaned |
| brand | Gigabyte | Gigabyte | json-ld |
| model | B650M Aorus Elite B650 | B650M Aorus Elite | json-ld.mpn |
| gtin | null | 4719331849818 | json-ld.gtin13 |
| price | 1199.99 | 1199.99 | json-ld |
| pix_price | null | 1199.99 | valVista+pix label |
| original_price | null | 1722.90 | precode del |
| installments | null | 12×117.65 | nParc/Parc |
| specifications | {} | 27 keys | accordion |
| images | 1 thumb | 6 gallery | /produto/g/ |
| promotion | countdown | countdown | preserved |
| canonical_url | clean path | clean path | fingerprints |

## Fetch after

| Métrica | Antes | Depois |
|---|---:|---:|
| HTTP attempts | 0 (skipped) | 1 curl_cffi |
| Browser fallback | always | only on challenge/miss |
| Proxy | rare | unchanged FALLBACK |
| Challenge on regression | no | no |
| Response bytes | ~200 KB (when Camoufox worked) | ~200 KB via HTTP |
| Duration (HTTP) | Camoufox seconds+ | ~250–300 ms |
