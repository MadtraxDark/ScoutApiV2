# TerabyteShop pricing semantics — 2026-09-24

## Ground truth (produto 22809)

| UI | Valor |
|---|---:|
| Pix / à vista | 1199.99 |
| Cartão (total) | 1411.75 |
| De (riscado) | 1722.90 |
| Parcelas | 12 × 117.65 |

## Fontes na PDP

| Fonte | Valor | Significado real |
|---|---:|---|
| JSON-LD `offers.price` | 1199.99 | **Pix/à vista** (não cartão) |
| `#valVista` | 1199.99 | Pix/à vista |
| `#valParc` | 1411.75 | **Total no cartão** |
| `#Parc` / `#nParc` | 117.65 / 12 | Parcela |
| `p.precode del` | 1722.90 | Preço anterior |
| Inline JS `$('.valParc')` / `$('.val-prod')` | iguais | Sync DOM |

## Causa raiz

Parser promovia JSON-LD (Pix) a `ProductOffer.price`. Cross-store (Pichau +
`product_registration_service`: `card = request.price`) define:

- `price` = cartão
- `pix_price` = Pix
- `original_price` = riscado ≠ cartão

## Depois

| Campo | Antes | Depois | Fonte |
|---|---|---|---|
| price | 1199.99 | **1411.75** | `#valParc` |
| pix_price | 1199.99 | **1199.99** | `#valVista` |
| original_price | 1722.90 | 1722.90 | precode del |
| installments | 12×117.65 | 12×117.65 | nParc/Parc |
| discount_percentage | 30.35 (vs Pix) | **18.06** (vs cartão) | original→card |
| card_price field | n/a | **não criado** — `price` é o cartão | — |

`metadata.pricing.pix_savings` = card − pix (211.76) — não misturado com
`discount_percentage`.

## Modelo / schema / DB / FE

- Sem novo campo `card_price` (contrato já usa `price` = cartão).
- Sem migration.
- Frontend PriceScout não está neste repo; mapeamento esperado permanece
  `price`→cartão / `pix_price`→Pix (igual Pichau).

## Multi-categoria

motherboard/cpu/gpu/ram/ssd: `pix < price(card)` e original só quando riscado
real no price box (GPU sem De → original null).
