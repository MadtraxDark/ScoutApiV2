# Amazon BR / US

Shared parsing core with thin regional spiders (`amazon_br`, `amazon_us`).
Store key is always `amazon`; markets stay separate via `country` / `currency`.

## Domains / markets

| Spider | Host | Country | Currency |
|---|---|---|---|
| `amazon_br` | `amazon.com.br` | BR | BRL |
| `amazon_us` | `amazon.com` | US | USD |

## Fetch strategy

HTTP-first progressive fetch (ADR 0016):

1. **HTTP** (`urllib`) with marketplace `Accept-Language` / Referer
2. Soft HTTP retry (~1.25s) when Buy Box widgets are missing without clear OOS
3. **Browser** (Camoufox) on HTTP error, challenge/robot-check, or non-PDP HTML
4. **Proxy** only after classified `UPSTREAM_BLOCKED` (Proxy Cost Mode FALLBACK)

Canonical fetch URL: `https://www.{host}/dp/{ASIN}` via `prepare_fetch_url`.

## Price / availability semantics

- `price` = Buy Box / primary offer only (never AOD / “outras ofertas”)
- Conditional pricing (Pix, Prime, Subscribe & Save, coupons, installments)
  stays in metadata — never promoted to `price`
- US availability is US-market stock, not shipping to Brazil
- Empty Buy Box without clear OOS → `MissingPriceError` (fail-closed)

## Known blocking behavior

- Robot check / `validateCaptcha` → `UPSTREAM_BLOCKED` (retryable; browser/proxy
  fallback per Proxy Cost Mode)
- Spiders refuse to parse challenge HTML as a product
- Hard-block may require proxy after classified block

## Important invariants

- Buy Box offer is the commercial truth for the scrape
- BR and US results must remain separate objects
- Conditional pricing stays conditional in metadata

## Known limitations

- HTTP-first covers `/crawl/offer` when the public PDP includes Buy Box
- BR HTML may omit Buy Box widgets intermittently (soft HTTP retry mitigates)
- Some ASINs return HTTP 500 for non-existent/blocked SKUs
- Official catalog API not used (eligibility / credentials)

## Live validation references

- US: `B09V9Z1WLN` — HTTP-first offer (~3s, no browser/proxy)
- BR Buy Box captures: `B0GY5SB1P3`, `B0GN4S2ZSK`, `B0GXLWFMQJ`

## Related

- ADR 0015 (multi-marketplace)
- ADR 0016 (HTTP-first)
- Fixtures: `tests/fixtures/amazon/`
- Tests: `tests/unit/test_amazon_*.py`
