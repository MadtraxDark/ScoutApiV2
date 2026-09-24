# TerabyteShop

## Markets / country

- `store=terabyteshop`, `country=BR`, `currency=BRL`
- Domain: `terabyteshop.com.br`

## Identifiers

- `product_id` from URL `/produto/{id}` (preferred) or numeric JSON-LD `sku` / `productID`
- JSON-LD `sku` often repeats the **brand name** — spider ignores non-numeric brand-as-sku and falls back to URL id
- `mpn` / `gtin13` from JSON-LD when present

## Live search (matching)

- Search: `matching.search_adapters` (PDP spider sem Search)
- SERP: `https://www.terabyteshop.com.br/busca?str={query}`
- Parser: links `/produto/{id}/…`
- Search uses HTTP-first (`prefer_browser=False`); same progressive fetcher as PDP

## Offer source

Priority for commercial totals:

| Campo | Significado | Fonte Terabyte |
|---|---|---|
| `price` | Preço **no cartão** / total comercial (cross-store; FE → “Preço no cartão”) | `#valParc` → JS `$('.valParc')` |
| `pix_price` | Total **Pix / boleto à vista** explícito | `#valVista` (label Pix/à vista/boleto) → JS `$('.val-prod')` → JSON-LD `offers.price` só como corroboração quando o label existe |
| `original_price` | Preço **anterior/referência** (“De” / riscado) no price box | `p.precode del` (escopo `#topopreco` / `.info-price`) — **válido mesmo se `< price(cartão)`**; não usar total parcelado para invalidar |
| `installment_count` / `installment_price` | Parcelas no cartão | `#nParc` / `#Parc` (+ JS) |
| `discount_percentage` | Desconto **promocional** `original → sale` (sale = Pix/à vista se houver, senão `price`) | derivado; **não** é economia Pix nem markup do cartão |

- JSON-LD `offers.price` nesta loja acompanha o **à vista/Pix**, não o cartão — **não** promover a `price` quando `#valParc` existe.
- **Não** inferir Pix por percentual (`price * 0.85`).
- **Não** mapear cartão → `original_price`.
- **Não** exigir `original_price > card_price` — relação de meio de pagamento ≠ referência “De”.
- Economia Pix (`card − pix`) fica em `metadata.pricing.pix_savings` quando ambos existem.
- Inconsistências observáveis (`original_lt_card`, `original_lt_pix`, …) em `metadata.pricing.consistency_warnings` — **não** apagam o original.
- Sem `#valParc`: last-resort (como Pichau) — usar à vista/Pix como `price` só se for a única oferta publicada.

## Frontend (PriceScout)

- Ofertas BRL em `app/admin/produtos/[id]/page.tsx`: “De …” só se `original_price !==` preço principal da linha (`rawOfferPrice` = Pix → cartão → original).
- Para o regressão 24707 (`original` 431,90 ≠ Pix 409,99) a UI mostra o “De” sem alteração de frontend.
- Preview de cadastro (`admin/page.tsx`) sempre exibe preço original quando presente.

## Details / specifications

- Title: JSON-LD `name` → `h1` → `<title>` (strip trailing `| Terabyte`)
- Brand: JSON-LD `brand` → accordion `Marca`
- Model: JSON-LD `mpn` → shared `ProductIdentity` resolver
- Specs: accordion `div.especificacoes` pairs `<p><strong>Label:</strong><br />value</p>` (generic label→value; no store-specific AM5/DDR5 normalization in the spider)
- Images: gallery `img.terabyteshop.com.br/produto/g/…` → JSON-LD `image` fallback (`/produto/p/` thumb)

## Timed promotion

- Campanhas com countdown jQuery:
  `$('#ctd{product_id}').countdown('YYYY/MM/DD HH:MM:SS')` em
  `America/Sao_Paulo`
- Spider emite `metadata.promotion` via `terabyte_promotion_from_html` /
  `extract_terabyte_countdown`
- Fallback fraco: JSON-LD `priceValidUntil` (fim do dia SP) só se não houver
  countdown

## Availability semantics

- JSON-LD `InStock` / `OutOfStock`; texto de indisponibilidade no body
- Challenge / incomplete HTML → technical error (`UPSTREAM_BLOCKED` / `ParseError`), never OOS

## Fetch strategy

1. **HTTP-first** — `TerabyteShopHttpFirstHtmlFetcher` + `curl_cffi` Chrome impersonation
2. Accept PDP when JSON-LD Product / `#valVista` / specs accordion present without challenge
3. Challenge / insufficient HTML → **Camoufox** (+ ADR 0017 resolution)
4. Proxy **FALLBACK** only after classified `UPSTREAM_BLOCKED` (Proxy Cost Mode)

Spider `_ensure_product_page()` remains a **safety net** (emits `UPSTREAM_BLOCKED` on Cloudflare “Just a moment”) — it must not be the primary escalation path.

`prepare_fetch_url` canonicalizes (strips `gclid` / `gbraid` / `gad_*`); ScrapeGuard cache keys already ignore tracking.

## Bypass / anti-block notes (2026-09-24)

| Técnica | Resultado |
|---|---|
| `urllib` / httpx plain | 403 Cloudflare frequente |
| `curl_cffi` impersonate Chrome | PDP HTML completo (~200 KB) + JSON-LD + countdown OK |
| Camoufox + resolução CF | Fallback se HTTP ainda devolver challenge |
| Mapear HTML CF → preço/promo | Inválido — resolver até PDP real |
| Sem HTTP-first (só Camoufox) | Regressão: falha de launch/browser ⇒ “não trouxe dados” mesmo com PDP HTTP válida |

## Known limitations

- Search/SERP pode variar layout; match depende de cards `/produto/`
- Sem countdown na PDP → monitor usa intervalo regular (12h), sem antecipação
- `variant` / atributos críticos (socket, chipset) vêm do identity layer compartilhado a partir das specs brutas — não hardcode de modelo na spider

## Tests

- `tests/unit/test_terabyteshop_spider.py`
- `tests/unit/test_terabyteshop_http_first.py`
- `tests/unit/test_terabyteshop_search_pdp_contract.py`
- `tests/unit/test_timed_promotion_wiring.py`
- HTML live de referência (dev only): `data/_terabyte_live.html` / `memory/working/_terabyte_probe/`
