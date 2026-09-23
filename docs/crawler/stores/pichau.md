# Pichau

## Markets / country

- `store=pichau`, `country=BR`, `currency=BRL`
- Domain: `pichau.com.br`
- Storefront: **Next.js App Router** + Magento GraphQL product embutido em
  `self.__next_f.push([1,"..."])` (RSC flight). Não há `__NEXT_DATA__` clássico.

## Identifiers

- `product_id` = Magento `id` numérico do blob RSC `product`
- `sku` = Magento `sku` (frequentemente o código de fabricante / MPN)
- `gtin` = `codigo_barra` quando presente
- `specifications.mpn` = mesmo `sku` Magento (não inventar MPN distinto)
- Fallback de slug na URL só quando o blob RSC não traz `sku`

## Live search (matching)

- Search: `matching.search_adapters` (PDP spider sem Search)
- SERP: `https://www.pichau.com.br/search?q={query}`
- Candidatos vêm de `url_key` no flight RSC (âncoras `<a>` do grid costumam
  **não** estar no SSR); filtra favoritos/account e slugs curtos
- PDP: path de um segmento `/slug-do-produto`

## Offer source priority

1. Blob RSC (flight unescape → objeto `product` com `pichau_prices`)
2. Tokens espalhados no HTML (escapados ou não)
3. JSON-LD `Product.offers` (fallback parcial)

### Pricing semantics

| Campo | Fonte |
|---|---|
| `price` | `pichau_prices.final_price` (cartão / preço comercial) |
| `pix_price` | `pichau_prices.avista` quando `avista_method=PIX` / presente |
| `original_price` | `pichau_prices.base_price` se **>** `price` |
| `installment_count` / `installment_price` | `max_installments` / `min_installment_price` |
| `discount_percentage` | `(original - price) / original` só com original real |

- **Não** promover PIX a `price` quando `final_price` existe (FE mapeia `price` →
  “Preço no cartão”).
- **Não** inferir PIX (`price * 0.9`) nem original a partir de desconto.
- **Não** promover parcela a `price`.

## Product details

- Título / brand: `product.name`, `marcas_info.name` → JSON-LD / `h1`
- Specs: atributos Magento escalares do blob (`socket`, `potencia`,
  `garantia`, `product_set_name`, categorias, …) + `mpn`/`gtin`
- Imagens (`include_images=true`): `media_gallery` → JSON-LD `image`
- Sem download binário só para listar URLs

## Timed promotion

- Blob pode expor `mysales_promotion.expire_at` em alguns SKUs; a PDP pública
  **não** é tratada como timer confiável de monitor — spider mantém
  `metadata.timed_promotion=false` e **não** inventa `metadata.promotion`
  (pesquisa 2026-09-21; revalidar se a UI passar a expor countdown estável)

## Availability

- `stock_status` RSC (`IN_STOCK` / `OUT_OF_STOCK`) → JSON-LD → assume available
  com preço

## Fetch strategy

- **HTTP-first (`curl_cffi`)** via `PichauHttpFirstHtmlFetcher`: SSR/RSC
  (~400KB+) com `pichau_prices` parseável sem Camoufox quando o HTML chega
  completo. `curl`/`urllib` plain costuma cair em **403 Cloudflare**; não usar
  como prova de “HTTP insuficiente” — impersonação TLS é o fast path.
- Challenge / HTML insuficiente / erro de rede → **Camoufox**
  (`StoreAwareHtmlFetcher` + ADR 0017 / 0018; proxy FALLBACK após bloqueio
  classificado)
- HTML de bloqueio ≠ produto: `UPSTREAM_BLOCKED`; nunca fabricar preço

## Parse quality / observability

- `metadata.parse_quality`: `rsc-complete` | `json-ld-fallback` | `partial`
- `metadata.source.*` registra origem de price / pix / original / installment /
  product blob
- Log `pichau_parse_quality=...` quando não for `rsc-complete`

## Known limitations

- Promo “especial” sem countdown UI confiável → sem antecipação de
  `next_check_at`
- SERP ainda é heurística de âncoras (sem título/preço no candidato)
- Layout RSC pode mudar; parser usa decode de flight + brace-scan (padrão
  Visão VIP), não classes CSS Emotion/MUI

## Tests

- `tests/unit/test_pichau.py`
- `tests/unit/test_timed_promotion_wiring.py`
- Fixtures: `tests/fixtures/pichau/`
- HTML de referência (dev): `data/_pichau_probe.html`
