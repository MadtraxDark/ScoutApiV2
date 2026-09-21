# Pichau

## Markets / country

- `store=pichau`, `country=BR`, `currency=BRL`
- Domain: `pichau.com.br`

## Identifiers

- Prefer Magento/`id` do blob RSC `product`
- `sku` do payload ou slug da URL (ex. `CP-9020295-BR`)

## Live search (matching)

- `supports_search=True`
- SERP: `https://www.pichau.com.br/search?q={query}`
- Links de PDP no domínio (slug sem `/search`)

## Offer source

- Prefer blob RSC embutido: `pichau_prices.avista` (PIX) → `final_price` →
  `special_price` → JSON-LD `offers.price`
- `original_price` = `base_price` quando maior que o preço escolhido

## Timed promotion

- **Sem timer estruturado** na PDP pública (pesquisa 2026-09-21)
- RSC / Magento expõe `special_price` e `pichau_prices`, mas **não**
  `special_to_date` / countdown / `expires`
- Spider marca `metadata.timed_promotion=false` e **não** inventa
  `metadata.promotion`
- Monitor usa só o intervalo regular (12h) para listings Pichau

## Pricing semantics

- Prefira à vista PIX (`avista`) quando presente
- Não promover parcela a `price`

## Availability semantics

- Flags/`is_in_stock` do blob; JSON-LD; fallback texto

## Fetch strategy

- HTTP-first (`curl_cffi`) retorna SSR/RSC grande (~400KB+) sem
  `__NEXT_DATA__` clássico — preço parseável no flight data
- Cloudflare / challenge / auth wall → **resolver** (Camoufox + ADR 0017 /
  0018; proxy FALLBACK após bloqueio classificado). Bypass obrigatório
- HTML de bloqueio ≠ produto: `UPSTREAM_BLOCKED` para continuar resolução;
  nunca fabricar preço/`expires_at`

## Bypass / anti-block notes (2026-09-21)

| Técnica | Resultado |
|---|---|
| HTTP plain | Pode 403 / HTML parcial |
| `curl_cffi` Chrome TLS | SSR/RSC com preços OK |
| Camoufox / auth bypass se challenge | Obrigatório até PDP real |
| Browser headed para achar timer XHR | Sem endpoint público de expiry; UI de desconto sem countdown confiável |
| Inventar `expires_at` a partir de `special_price` | Inválido (dado inexistente) — não confundir com bloqueio |

## Known limitations

- Promo “especial” sem data de fim → sem antecipação de `next_check_at`
  (limitação de dados, não de bypass)
- Layout Next/RSC pode mudar; parser tolera blob aninhado + tokens
  `avista`/`special_price`

## Tests

- `tests/unit/test_timed_promotion_wiring.py`
- HTML de referência: `data/_pichau_probe.html` (dev only)
