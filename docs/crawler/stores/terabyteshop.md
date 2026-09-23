# TerabyteShop

## Markets / country

- `store=terabyteshop`, `country=BR`, `currency=BRL`
- Domain: `terabyteshop.com.br`

## Identifiers

- `product_id` from URL `/produto/{id}` or JSON-LD `sku` / `productID`

## Live search (matching)

- Search: `matching.search_adapters` (PDP spider sem Search)
- SERP: `https://www.terabyteshop.com.br/busca?str={query}`
- Parser: links `/produto/{id}/…`

## Offer source

- Prefer JSON-LD `Product.offers.price`
- Fallback: inline JS `'price': N.NN`

## Timed promotion

- Campanhas com countdown jQuery:
  `$('#ctd{product_id}').countdown('YYYY/MM/DD HH:MM:SS')` em
  `America/Sao_Paulo`
- Spider emite `metadata.promotion` via `terabyte_promotion_from_html` /
  `extract_terabyte_countdown`
- Fallback fraco: JSON-LD `priceValidUntil` (fim do dia SP) só se não houver
  countdown

## Pricing semantics

- `price` = oferta atual (JSON-LD / JS)
- `original_price` = preço “De” maior que `price`, quando presente no HTML

## Availability semantics

- JSON-LD `InStock` / `OutOfStock`; texto de indisponibilidade no body

## Fetch strategy

- HTTP-first (`curl_cffi` Chrome impersonation) costuma bastar
- Cloudflare / challenge → **resolver** (Camoufox + ADR 0017; proxy
  FALLBACK só após `UPSTREAM_BLOCKED` classificado). Bypass/resolução são
  obrigatórios — não abortar na detecção
- HTML de challenge ≠ PDP: spider emite `UPSTREAM_BLOCKED` para o fetch
  continuar resolução; nunca fabricar oferta/`metadata.promotion`

## Bypass / anti-block notes (2026-09-21)

| Técnica | Resultado |
|---|---|
| `urllib` / httpx plain | 403 Cloudflare frequente |
| `curl_cffi` impersonate Chrome | PDP HTML completo + countdown OK |
| Camoufox + resolução CF | Obrigatório se HTTP ainda devolver challenge |
| Mapear HTML CF → preço/promo | Inválido — resolver até PDP real |

## Known limitations

- Search/SERP pode variar layout; match depende de cards `/produto/`
- Sem countdown na PDP → monitor usa intervalo regular (12h), sem antecipação

## Tests

- `tests/unit/test_timed_promotion_wiring.py`
- HTML live de referência: `data/_terabyte_live.html` (dev only)
