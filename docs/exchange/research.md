# Câmbio — pesquisa e decisão semântica (PriceScout)

Documento canônico da pesquisa pré-implementação. Decisão arquitetural:
[ADR 0034](../adr/0034-secondary-exchange-rates.md).

## 1. Problema

O PriceScout precisa responder:

> Se este produto custa X na moeda da loja, quanto X representa
> **aproximadamente** em reais pela cotação atual?

Fórmula:

```text
FOREIGN PRICE × EXCHANGE RATE = BRL REFERENCE VALUE
```

Isso **não** é o custo final de compra/importação e **não** é necessariamente
`foreign_price × forex_midpoint`.

**Fora do cálculo (sempre):** IOF, imposto de importação, ICMS, sales tax,
frete, tarifa de cartão/banco/remessa, custo de viagem, alfândega.

Separação arquitetural obrigatória:

```text
ExchangeRate  ≠  Tax  ≠  ImportCost  ≠  Shipping  ≠  FinalCost
```

Este módulo só resolve **ExchangeRate** (item 1).

## 2. Compra vs venda (terminologia)

Do ponto de vista da **instituição** (banco / casa de câmbio):

| Lado na tabela | Quem faz o quê | Taxa típica |
|---|---|---|
| **Compra** | Instituição **compra** a moeda estrangeira do cliente (cliente vende USD) | mais baixa |
| **Venda** | Instituição **vende** a moeda estrangeira ao cliente (cliente compra USD) | mais alta |

O usuário do PriceScout que precisa **adquirir** USD (espécie, cartão pré-pago,
ou referência de custo de compra internacional) está no lado da **venda** da
instituição.

**Decisão:** a taxa de negócio USD→BRL **não** se chama `buy`. O `rate_type`
canônico é `tourism_sell` (dólar turismo — venda).

## 3. Comercial × turismo × PTAX × spread × espécie × cartão

| Conceito | O que é | Uso no PriceScout |
|---|---|---|
| **Dólar comercial** | Mercado interbancário / empresas | referência; **não** é custo varejo |
| **PTAX** | Média ponderada BCB (compra/venda) do comercial | auditoria + validação; `ptax_sell` |
| **Dólar turismo** | Cotação varejo (espécie / turismo) com spread | **taxa de negócio** USD→BRL |
| **Spread** | Diferença compra/venda da instituição | embutido em turismo; não inventamos % |
| **Espécie** | Dinheiro físico | turismo é o proxy público |
| **Cartão internacional** | Taxa do emissor (± comercial) **+ IOF** | IOF **fora** de ExchangeRate |
| **VET (BCB)** | Custo efetivo com tarifas e tributos | rejeitado aqui — mistura imposto |

Evidência Valor Data (2026-09-22): turismo venda ≈ 5,30 vs PTAX venda ≈ 5,12
(~3–4% acima do comercial) — coerente com spread varejo.

## 4. Estados Unidos

- Ofertas: Amazon US / Best Buy → `currency=USD`.
- Conversão: `amount_USD × tourism_sell`.
- PTAX/comercial ficam persistidos para auditoria, não como default de UI.

## 5. Paraguai

### Moeda e precificação nas lojas ScoutApiV2

| Loja | Country | Currency real |
|---|---|---|
| Visão VIP | PY | **USD** (fixo) |
| Nissei | PY | **PYG** default; PDPs `/br/` frequentemente **USD** |
| Shopping China | PY | **PYG** (`.com.py`) / **BRL** (`.com.br`); USD tax-free em `metadata.display_prices` |

Fontes: spiders + `docs/crawler/stores/*`. **Sempre** usar `Offer.currency`,
nunca inferir só pelo país.

### Comportamento de mercado (pesquisa)

- Eletrônicos em CDE costumam ser anunciados em **USD**.
- Brasileiros pagam USD espécie, BRL (taxa da loja), Pix ou cartão — cada um
  com cotação própria (Melhores Destinos: lojas ~R$ 5,19–5,25/USD quando
  comercial estava ~R$ 5,07).
- Moeda oficial: **PYG** (guaraní). USD é moeda comercial de fronteira.
- BCP publica cotização referencial diária: USD/PYG e **BRL** (₲ por BRL).
- BCB publica **Taxa SML** Real/Guarani (sistema de pagamentos).

### Pares necessários

| Par | Necessário? | Motivo |
|---|---|---|
| USD/BRL | **Sim** | Amazon US, Best Buy, Visão VIP, Nissei USD |
| PYG/BRL | **Sim** | Nissei/Shopping China em PYG |
| USD/PYG | **Sim (auditoria)** | validação / cross-rate opcional |

Default PYG→BRL: taxa **oficial BCP** invertida da coluna ₲/ME da linha BRL
(`rate = 1 / guaranies_per_brl`), `rate_type=official`.

Cross-rate turismo: `tourism_sell / usd_pyg` — documentado; **não** é o
default (mistura varejo BR com referencial PY e pode divergir do SML/BCP).

### Bid/ask em cross-rate

Para estimar BRL necessários a partir de PYG via USD:

1. PYG → USD com taxa referencial BCP (`USD = PYG / USD_PYG`).
2. USD → BRL com **`tourism_sell`** (BRL pagos para obter 1 USD).

Não misturar `tourism_buy` com PTAX venda nem inverter lados.

## 6. Fontes pesquisadas

### Oficiais / institucionais

| Fonte | URL / acesso | Conteúdo | Key? |
|---|---|---|---|
| BCB OLINDA PTAX | `olinda.bcb.gov.br/.../PTAX` | USD compra/venda comercial | Não |
| BCB SML PY | página SML | Real/Guarani oficial | Não |
| BCB Ranking VET | REST v2 | custo com tarifas/tributos | Não (fora do escopo) |
| BCP cotización | HTML tabela `#cotizacion-interbancaria` | USD/PYG, BRL/PYG… | Não |

### Agregadores públicos (HTML)

| Fonte | Conteúdo | Notas |
|---|---|---|
| **Valor Data / Valor Investe** | Turismo (tabela Compra/Venda quando SSR; senão ticker `USDBRLT_VALR` como `tourism_sell`) + PTAX embed | Primary turismo; robots não bloqueia `/valor-data/` para UA genérico; HTML da tabela pode mudar — provider tem fallback |
| InfoMoney ferramentas/câmbio | Comercial (toolData JSON) | Sem turismo estável na página analisada |
| UOL cotacoes | Página grande, dados via JS/API | API host instável/403 no probe |
| Melhor Câmbio | Comparador casas | Shell JS; scrape Selenium nos projetos OSS — rejeitado (browser) |
| AwesomeAPI `USD-BRLT` | Turismo JSON | **Rejeitada** (API gratuita com quota/cadastro) |
| Frankfurter / AllRatesToday | wrappers BCP | **Rejeitadas** (API de câmbio / chave) |

### Critérios de seleção (aplicados)

Confiabilidade, atualização, compra/venda, timestamp, HTML/JSON estável,
sem auth/CAPTCHA/custo, validável contra segunda fonte.

## 7. Projetos GitHub / comunidade

| Projeto | Abordagem | Lição |
|---|---|---|
| [wilsonfreitas/python-bcb](https://github.com/wilsonfreitas/python-bcb) | Cliente OLINDA PTAX | Preferir OData oficial a scrape frágil do conversor |
| [acpguedes/BCScrapper](https://github.com/acpguedes/BCScrapper) | Scrape BCB | Pouca manutenção; OLINDA é superior |
| DevElthon/commodities_autosearch, Thamyresmya/Automacao_Web | Selenium Melhor Câmbio | Browser desnecessário para FX leve |
| leonardoaj/cotacoes-infomoney | ChromeDriver histórico | HTML frágil; útil só como alerta de manutenção |

Stack Overflow: reforço de **Decimal puro** (sem float) e cuidado bid/ask.
Reddit (`r/Paraguay`, `r/viagens`): USD espécie em CDE; notas “perfeitas”;
Pix/cartão com spread de loja — confirma que taxa única não captura loja a
loja.

## 8. Providers adotados

| Papel | Provider | Pares / tipos | Frequência observada |
|---|---|---|---|
| Primary USD turismo | `ValorDataProvider` | `tourism_buy`, `tourism_sell` (+ PTAX da mesma página para acordo) | intradiário (minutos) |
| Secondary / oficial USD comercial | `BcbPtaxProvider` | `ptax_buy`, `ptax_sell` | 1×/dia útil (fechamento) |
| Primary PYG | `BcpReferentialProvider` | `USD/PYG official`, `PYG/BRL official` | 1×/dia útil |
| Secondary PYG/BRL | `BcbSmlProvider` | `PYG/BRL official` (SML) | 1×/dia útil |

Refresh operacional: **30 minutos** (não a cada segundo; respeita fontes).
Stale: cotação com idade > **6 horas** → `status=stale` (ainda servível).

Tolerância de acordo PTAX (Valor vs BCB): **0,5%**. Turismo deve ficar entre
`ptax_sell` e `ptax_sell × 1,12` (outlier — não inventa valor).

## 9. Terminologia na UI

- USD: **“Dólar turismo (venda)”** — não “cotação de compra”.
- PYG: **“Cotação referencial (BCP)”**.
- Exibir idade / `stale` quando aplicável.

## 10. Limitações aceitas

- Não modela taxa própria Nissei/Shopping China/Cellshop.
- Não inclui IOF, frete, imposto de importação, sales tax.
- Turismo Valor é agregação de mercado varejo, não uma casa específica.
- BCP/SML são referenciais oficiais, não cambista de ponte.
