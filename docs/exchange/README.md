# Câmbio (ExchangeRate) — ScoutApiV2

Subsistema **secundário** de cotação para converter preços estrangeiros em BRL
de referência no PriceScout.

## O que esta função responde

> Se o produto custa X na moeda da loja, quanto X representa **aproximadamente**
> em reais pela cotação atual?

Fórmula única:

```text
FOREIGN PRICE × EXCHANGE RATE = BRL REFERENCE VALUE
```

**Não** é custo final de compra/importação.

## O que NÃO entra no cálculo

IOF, imposto de importação, ICMS, sales tax, frete, tarifa de cartão, tarifa
bancária, taxa de remessa, custo de viagem, alfândega — nem qualquer outro
encargo. Isso ficaria em serviços futuros (`Tax` / `ImportCost` / `FinalCost`).

## Semântica da cotação

- **USD→BRL (negócio):** `tourism_sell` — lado **venda** da instituição
  (cliente com reais adquirindo USD). Não usar o nome `buy` só porque a
  pergunta de negócio fala em “compra”.
- **PYG→BRL (negócio):** `official` (BCP).
- Oferta paraguaia em **USD** → conversão **direta** USD→BRL (nunca
  USD→PYG→BRL sem necessidade).
- Sempre respeitar `Offer.currency`.

Pesquisa completa: [`research.md`](research.md). ADR: [`../adr/0034-secondary-exchange-rates.md`](../adr/0034-secondary-exchange-rates.md).

## Fluxo

```text
fontes públicas (HTTP)
  → ExchangeRateRefreshService (scheduler DB-driven)
  → PostgreSQL (latest + observations)
  → convert() / attach_conversion()
  → converted_price_brl na API (price/currency originais intactos)
```

Falha de câmbio **não** derruba crawler/match/produtos. Usa last-known-good
com `exchange_rate_status=stale`, ou `converted_price_brl=null` se nunca houve
taxa.

## Endpoints

| Método | Path | Auth |
|---|---|---|
| GET | `/exchange-rates` | `products:read` |
| GET | `/exchange-rates/diagnostics` | admin |
| POST | `/exchange-rates/refresh` | admin |

Worker: `python -m scout_api.modules.exchange.worker` (script `scout-exchange`).
