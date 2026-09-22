# ADR-0034: Câmbio secundário sem API comercial (providers web + PostgreSQL)

- Status: Accepted
- Data: 2026-09-22

## Contexto

O PriceScout compara ofertas no Brasil, EUA e Paraguai. Ofertas
internacionais chegam com `price` + `currency` (USD/PYG) e o usuário precisa
de uma estimativa em BRL. Câmbio é **secundário**: falha não pode derrubar
crawler, match nem persistência de ofertas.

Restrições explícitas: sem API SaaS de câmbio (Fixer, ExchangeRate-API,
AwesomeAPI, etc.), sem API key, gratuito, HTTP leve (sem Camoufox),
persistência PostgreSQL, scheduler DB-driven (mesmo espírito do ADR 0030).

## Problema / decisão necessária

1. Qual taxa representa “quanto custa, em reais, comprar esse produto nesse
   mercado?” — e não o midpoint forex.
2. Como obter USD/BRL e PYG/BRL de fontes públicas sem vendor de FX.
3. Como separar ExchangeRate de impostos/frete/IOF.

## Alternativas consideradas

### A — API comercial/gratuita de câmbio (Fixer, OER, AwesomeAPI, Frankfurter…)

Rejeitada: quota/chave, dependência externa de FX SaaS, e várias entregam
apenas midpoint de mercado — semanticamente inadequado para custo de
aquisição de moeda pelo consumidor.

### B — Scrape de uma única fonte HTML

Rejeitada como SoT única: HTML muda, risco de downtime silencioso, sem
validação cruzada.

### C — Múltiplos providers web públicos + persistência + last-known-good

Adotada: providers institucionais/públicos (Valor Data turismo, BCB PTAX
OLINDA, BCP referencial, BCB SML), validação/outlier, histórico, status
`fresh|stale|unavailable`, scheduler com `next_refresh_at` no PostgreSQL.

### D — Configuração manual `USD_BRL=…` no `.env`

Rejeitada como modo normal (override só testes/emergência). Desatualiza e
não escala.

## Decisão

- Introduzir módulo `scout_api.modules.exchange` (feature package).
- **Taxa de negócio USD→BRL:** `tourism_sell` (cotação de **venda** turismo —
  o lado em que a instituição **vende** USD ao consumidor). Conversão =
  `price × rate` **sem** IOF/impostos/frete/tarifas.
- **Taxa de negócio PYG→BRL:** `official` do Banco Central do Paraguai
  (linha BRL da planilha referencial), com fallback SML BCB.
- Persistir também `ptax_sell`/`ptax_buy` e pares USD/PYG para auditoria e
  validação — nunca misturar IOF/frete/imposto na mesma abstração.
- Conversão **não** sobrescreve `price`/`currency` da Offer; expõe
  `converted_price_brl` + metadados de câmbio.
- Oferta paraguaia em USD → USD→BRL **direto** (nunca USD→PYG→BRL sem
  necessidade).
- Refresh periódico leve (HTTP); falha → last-known-good + `stale`.

Detalhes de pesquisa, fontes e semântica:
[`docs/exchange/research.md`](../exchange/research.md).

## Justificativa

Alinha o significado financeiro ao PriceScout, cumpre “sem API de câmbio”,
reusa o padrão de relógio persistente do projeto e degrada com segurança.

## Consequências positivas

- Comparação comercial USD/PYG → BRL auditável e tipada (`rate_type`).
- Restart não perde cotação; fontes respeitadas (intervalo longo).
- Separação clara ExchangeRate ≠ Tax ≠ Shipping ≠ FinalCost.

## Trade-offs / consequências negativas

- HTML do Valor Data pode mudar (parser deve falhar explicitamente).
- Turismo publicado por agregador ≠ cotação de uma casa específica nem VET
  (VET inclui tributos — fora do escopo de ExchangeRate).
- Cotação referencial PYG não captura spread de cambista de fronteira nem
  taxa própria de cada loja paraguaia.
