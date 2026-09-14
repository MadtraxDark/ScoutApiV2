# Magazine Luiza

## Markets / country

- `store=magazineluiza`, `country=BR`, `currency=BRL`
- Domain: `magazineluiza.com.br`

## Identifiers

- Product identity from `__NEXT_DATA__` item / fallbacks

## Live search (matching)

- `supports_search=True`
- SERP: `https://www.magazineluiza.com.br/busca/{query}/`
- Parser: product card `/p/{id}/` links
- Used by `POST /match` (ADR 0019)

## Offer source

- `__NEXT_DATA__` item + `offers[]`
- If URL has `seller_id`, bind to that seller’s offer; otherwise first offer

## Details source

- Item catalog fields + specs; color often as Magalu raw label

## Images source

- Gallery when `include_images=true` (store supports images)

## Pricing semantics

- Pix from `bestPrice` when `paymentMethodId == pix`, else visible “no pix”, else JSON-LD
- Do not invent Pix

## Availability semantics

- Fail-closed: missing clear stock signal → `ParseError` (not soft unavailable)

## Seller / marketplace

- Prefer seller id / delivery identifiers over display-only names when selecting offers

## Fetch strategy

- Default Camoufox + Proxy Cost Mode

## Known blocking

- Akamai Bot Manager **sec-cpt / behavioral** interstitial
  (`sec-if-cpt-container`, ~2–3 KB stub) — detected as challenge (ADR 0017)
- Resolver: origin warmup + Camoufox pointer wander / press-and-hold; on failure
  → `UPSTREAM_BLOCKED` → proxy fallback (Proxy Cost Mode)
- Fetcher challenge / hard-block classification must precede spider parse
  (never map interstitial HTML to missing price)

## Important invariants

- Selected seller must match URL `seller_id` when present
- First true Offer/Details split in the project (ADR 0011)

## Known limitations

- NEXT_DATA schema drift breaks selection
- **Produto / URL inexistente ou aposentado** (não é falha da integração Magalu):
  IDs mortos ou URLs curtas inválidas (ex. histórico `/p/240590700/`) podem
  soft-redirect para home (sem `data.item`) ou render soft-404 `h1=Oops!` com
  título genérico. O spider classifica como `ParseError` (“soft-404”) e **não**
  monta produto com `title=Oops!` / preço fabricado. Em validação live, se
  aparecer Oops/soft-404, **teste outro PDP válido e disponível** no site antes
  de tratar como regressão do crawler (ex. referência viva:
  Galaxy Tab S10 Lite `/p/jjhd6g4f9d/…?seller_id=samsung`).
- Akamai behavioral scoring is adversarial; residential BR proxy may still be
  required after local resolution attempts

## Live validation references

- Soft-404 (URL inválida, **não** integração): `/p/240590700/` → `ParseError` soft-404
- PDP viva (2026-09-14): Galaxy Tab S10 Lite
  `…/p/jjhd6g4f9d/tb/sams/?seller_id=samsung` → oferta OK
  (`price`/`pix_price`/`seller=samsung`/`available`)
- Outras PDPs válidas já observadas: `/p/238803000/`, `/p/241268000/`

## Tests / fixtures

- `tests/fixtures/magazineluiza/` (incl. `product_oops_soft_404.html` para
  classificação de URL morta — não representa falha de loja),
  coverage in `tests/unit/test_spider_parsing.py`
- Akamai sec-cpt detection/resolution: `tests/unit/test_html_fetcher.py`,
  `tests/unit/test_challenge_resolution.py`
