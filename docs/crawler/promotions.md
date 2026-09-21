# Promoções temporizadas por loja

Pesquisa de suporte a **expiration confiável** para monitoramento
(ADR 0030). Só marcar “sim” com evidência.

| Store | Timed promotion? | Source | Structured expiration? | SKU-specific? | Tested |
|---|---|---|---|---|---|
| TerabyteShop | **Sim** (campanhas com “Termina em”) | HTML + jQuery Countdown `$('#ctd{id}').countdown('YYYY/MM/DD HH:MM:SS')` | **Sim** (datetime local `America/Sao_Paulo`) | Por `product_id` (`ctd{id}`) | Live HTML 2026-09-21 (PDP 41251 → `2026/09/28 10:00:59`) |
| Pichau | **Inconclusivo / não no SSR** | Next.js chunks; JSON-LD preço sem timer; `special_price` token fraco | **Não** encontrado no HTML inicial | Desconhecido | Live HTML 2026-09-21 — sem countdown/API pública no documento estático; precisa browser/XHR |
| Mercado Livre | **Sim** (Oferta Relâmpago / deals) | Seller Promotions API `finish_date`; às vezes JSON embutido no PDP | Sim (API autenticada seller; PDP parcialmente) | Por item | Docs oficiais ML; extractor HTML heurístico disponível; spider atual ainda não emite `metadata.promotion` |
| Shopee | **Sim** (Oferta Relâmpago / flash) | Payload tipicamente `end_time` unix + `model_id` | Sim quando flash está no payload | Sim (model/SKU) | Fixtures atuais sem flash; extractor regex + `metadata.promotion` prontos |
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

O monitor lê via `observation_from_metadata` / extractors HTML.
Sem expiry absoluto → **não** inventar countdown.

## Terabyte (evidência)

Script jQuery na PDP:

```js
$('#ctd41251').countdown('2026/09/28 10:00:59')
```

Extractor: `extract_terabyte_countdown`.

## Pichau (evidência)

SSR ~420 KB sem `__NEXT_DATA__`, sem `countdown`/`expires`/`special_to_date`.
Preço via JSON-LD. Timer (se existir na UI) provavelmente hidratado via
chunk/XHR — **não** tratado como confiável até fonte estruturada.

## Expiração no domínio

- `promotion_status`: `none` | `active` | `expired`
- Expirado: não apresentar como promo vigente; preservar payload/eventos
- `next_check_at` antecipado para revalidar preço real
