# TerabyteShop original_price semantics — 2026-09-24

## Regression URL

https://www.terabyteshop.com.br/produto/24707/placa-mae-gigabyte-a520m-k-v2-chipset-a520-amd-am4-matx-ddr4

## Before

| Campo | Valor | Fonte |
|---|---|---|
| price (cartão) | 482.34 | #valParc |
| pix_price | 409.99 | #valVista |
| original_price | **null** | absent (descartado) |
| installments | 12 × 40.20 | nParc/Parc |
| DOM De | R$ 431,90 | p.precode del (presente!) |

## Root cause

`_original_price()` required `money > price` where `price` is **card** total.
Here `431.90 < 482.34` → silent drop.

## After

| Campo | Valor | Fonte |
|---|---|---|
| price | 482.34 | #valParc |
| pix_price | 409.99 | #valVista |
| original_price | **431.90** | dom-precode-del |
| discount_percentage | 5.07 | original → pix |
| consistency_warnings | original_lt_card | observability |

Relation: pix (409.99) < original (431.90) < card (482.34) — all preserved.

## Fix

- Accept semantic De/strikethrough without comparing to card/installments
- Scope still limited to main price box
- `discount_percentage` = original → sale (Pix if present)
- Warnings in `metadata.pricing.consistency_warnings` (do not null out)
- `docs/crawler/contracts.md` updated (original is semantic; not “must be > price”)

## Frontend (PriceScout)

- Hide “De” only when `original_price ===` principal line (`rawOfferPrice`: Pix → card)
  in `app/admin/produtos/[id]/page.tsx` — equality, not `<= card`.
- 24707: 431.90 ≠ 409.99 Pix → UI shows “De” once API returns original; **no FE change**.
- Audits: [Inspect PDP 24707](63769600-dcb5-4743-ab80-c7eed211cd82),
  [Audit FE original_price hide](c16678a1-a616-451c-b6f4-c9736e4d71d3).
