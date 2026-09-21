# Promoções temporizadas por loja

Pesquisa de suporte a **expiration confiável** para monitoramento
(ADR 0030). Só marcar “sim” com evidência.

| Store | Timed promotion? | Source | Structured expiration? | SKU-specific? | Tested |
|---|---|---|---|---|---|
| TerabyteShop | **Sim** (campanhas com “Termina em”) | HTML + jQuery Countdown `$('#ctd{id}').countdown('YYYY/MM/DD HH:MM:SS')` | **Sim** (datetime local `America/Sao_Paulo`) | Por `product_id` (`ctd{id}`) | Live HTML 2026-09-21; spider emite `metadata.promotion` |
| Pichau | **Não** (preço promo sem timer) | RSC `special_price` / `pichau_prices`; sem `special_to_date` | **Não** — confirmado SSR + RSC 2026-09-21 | N/A | Spider `implemented=True`; `timed_promotion=false` |
| Mercado Livre | **Sim** (Oferta Relâmpago / deals) | `lightning_deal_configuration.finish_date` no HTML/JSON embutido; Seller API (seller-only) | Sim quando o bloco está no PDP | Por `item_id` | Spider emite `metadata.promotion` quando presente |
| Shopee | **Sim** (Oferta Relâmpago / flash) | Payload `flash_sale` / `deep_discount` `end_time` unix | Sim quando flash está no payload da model/item | Sim (model/SKU) | Spider emite `metadata.promotion`; fixtures sem flash → sem campo |
| KaBuM | **Parcial** | Área “Oferta Relâmpago” no site; PDP comum pode ser só desconto | Não confirmado structured no spider atual | Desconhecido | Sem evidência de timestamp no parser atual |
| Magazine Luiza | Não evidenciado | Preço/original/pix | Não | — | Spider não extrai timer |
| Amazon BR | Não evidenciado como countdown de oferta | Deal badges variáveis | Não no contrato atual | — | — |
| Amazon US | Não evidenciado | Idem | Não | — | — |
| AliExpress | Condicional (cupom/campaign tags) | `metadata.promotions` | Geralmente **sem** end absoluto confiável no path atual | Tags/campaign | Parser grava condições, não força timer |
| Shopping China | Não evidenciado | — | Não | — | — |
| Nissei | Não evidenciado | — | Não | — | — |
| Visão VIP | Preço promo sem timer | `productPromotionPrice` | Não | — | Docs loja |
| Best Buy | Não evidenciado | — | Não | — | — |
| eBay / GameStop / Newegg / Micro Center / Cellshop / Star Games | Placeholder / não implementado | — | — | — | — |

## Contrato de metadata

Spiders que tiverem expiry confiável devem preencher:

```json
{
  "promotion": {
    "type": "flash_sale",
    "expires_at": "2026-09-21T18:00:00Z",
    "starts_at": null,
    "timezone": "America/Sao_Paulo",
    "source": "store.payload",
    "sku": optional,
    "product_id": optional,
    "conditions": { "pix": true }
  }
}
```

Helpers: `scout_api.modules.crawler.utils.timed_promotion`.
O monitor lê via `observation_from_metadata` / extractors HTML.
Sem expiry absoluto → **não** inventar countdown.

## Terabyte (evidência)

Script jQuery na PDP:

```js
$('#ctd41251').countdown('2026/09/28 10:00:59')
```

Extractor: `extract_terabyte_countdown` → spider
`TerabyteShopSpider.extract_offer`.

## Pichau (evidência)

SSR/RSC com `special_price` e PIX à vista, **sem** countdown/`expires`.
Limitação aceita documentada em [`stores/pichau.md`](stores/pichau.md).

## Mercado Livre

Quando o PDP real contém `lightning_deal_configuration.finish_date`, o
spider anexa `metadata.promotion` (tipo `lightning_deal`). Página de
deals lista o mesmo campo. Se a resposta for Snoopy/challenge: **resolver
obrigatoriamente** (Camoufox + ADR 0017; auth wall ADR 0018 se aplicável;
proxy só após bloqueio classificado). Só então extrair o timer do HTML de
oferta — nunca mapear challenge para produto/promo.

## Shopee

`shopee_flash_promotion` lê `flash_sale` / `deep_discount` no payload
`get_pc`. Sem bloco flash → oferta normal sem `metadata.promotion`.

## Bypass / bloqueios (pesquisa 2026-09-21)

Challenge, CAPTCHA, soft-block e login wall **devem ser resolvidos**
(ADR 0017 / 0018). É **proibido** tratar “só detectar e abortar” ou
“proibir bypass” como política. `UPSTREAM_BLOCKED` só depois de esgotar
resolução. Nunca inventar preço/`expires_at` a partir de HTML de bloqueio.

| Situação | Técnica obrigatória / preferida |
|---|---|
| Cloudflare 403 HTTP plain | `curl_cffi` Chrome TLS/HTTP2 impersonation; se persistir → Camoufox + resolução |
| ML Snoopy PoW (HTTP 200 fino) | **Resolver** com Camoufox (ADR 0017); auth bypass se wall (ADR 0018) |
| Shopee `/verify/traffic` | Auth bypass operador + `ProxyPolicy.FALLBACK` (`stores/shopee.md`) |
| CF “Just a Moment” Terabyte/Pichau | Classificar challenge → Camoufox / retry / proxy FALLBACK até PDP real |
| Pichau sem timer estruturado | Limitação de dados (sem expiry) — **não** é desculpa para pular bypass de bloqueio |

Proxy pago continua só após `UPSTREAM_BLOCKED` classificado (Proxy Cost Mode).

## Expiração no domínio

- `promotion_status`: `none` | `active` | `expired`
- Expirado: não apresentar como promo vigente; preservar payload/eventos
- `next_check_at` antecipado para revalidar preço real
