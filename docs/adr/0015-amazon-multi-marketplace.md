# ADR 0015: Amazon multi-marketplace — shared core + regional adapters

- Status: Accepted
- Data: 2026-09-12

## Contexto

O ScoutApiV2 precisa coletar ofertas da Amazon no Brasil (`amazon.com.br`) e
nos Estados Unidos (`amazon.com`). O mesmo ASIN (ou o mesmo modelo físico)
pode ter preços, moedas, sellers, Buy Box, disponibilidade, variantes e
promoções diferentes em cada marketplace. A arquitetura do crawler já usa
`store` + `country` + `currency` por oferta (`ProductOffer`) e um spider por
domínio sob pastas regionais.

Pesquisa externa (PA-API/Creators API, scrapers open source multi-marketplace,
provedores terceiros e artigos técnicos) mostra um padrão dominante: **um
parser parametrizado por marketplace**, com ASIN/variantes/imagens
compartilhados e diferenças locais (labels, moeda, Pix vs Prime) via
configuração. APIs oficiais exigem conta Associates + elegibilidade contínua
(ex.: vendas qualificadas) e não cobrem o caso Scout sem aprovação. Provedores
pagos adicionam lock-in e custo fora do Proxy Cost Mode.

## Problema / decisão necessária

Como representar Amazon BR e US no ScoutApiV2 sem misturar ofertas entre
mercados, sem duplicar parsers e sem introduzir frameworks internacionais
prematuros?

## Alternativas consideradas

- **A — Adapter único regionalizado:** um spider com `if marketplace` para
  BR/US.
- **B — Dois adapters regionais + helpers compartilhados:** spiders finos
  BR/US com `store="amazon"` e módulo comum (ASIN, variantes, imagens,
  bloqueio).
- **C — Shared core + Strategy/Factory formal:** hierarquia
  `AmazonMarketplaceStrategy` com subclasses.
- **D — API oficial (PA-API / Creators API):** credenciais Associates,
  elegibilidade, ToS afiliado; não integrar sem aprovação.
- **E — Provider terceirizado de dados Amazon:** custo, vendor lock-in; não
  adicionar sem autorização.

## Decisão

Adotar **B (dois adapters regionais finos + core compartilhado)**:

1. `store="amazon"` em ambos; `country`/`currency` vêm do marketplace da URL
   (`BR`/`BRL` vs `US`/`USD`).
2. Duas entradas `StoreConfig` (chaves de catálogo `amazon_br` / `amazon_us`)
   com `StoreConfig.key == "amazon"` e domínios distintos, para proxy/métricas
   resolverem por host sem criar lojas `amazon_br`/`amazon_us` no contrato
   público.
3. Spiders: `AmazonBrazilSpider` e `AmazonUSSpider` sob
   `spiders/brazil/` e `spiders/usa/`, delegando a
   `spiders/amazon/` (ASIN, URL canônica, Buy Box, variantes, imagens,
   challenge).
4. Ofertas são sempre independentes: nunca compartilhar preço/seller entre
   mercados; sem conversão cambial no spider.
5. Availability US segue a semântica Best Buy (ADR 0013): estoque do
   marketplace US, não “envia para o Brasil”.
6. `product_id` e `sku` = ASIN da variante selecionada; parent ASIN e
   fulfilled-by em metadata quando aplicável.
7. Bloqueio/CAPTCHA → tentar **resolver** (ADR 0017); `RequestError(UPSTREAM_BLOCKED)`
   só após esgotar resolução; nunca `available=false` a partir de HTML de challenge.

## Justificativa

- O código realmente compartilhado (ASIN, twister, galeria, challenge) é
  grande; diferenças regionais (Pix/parcelas BR, Prime/Subscribe US, labels)
  são pequenas o bastante para config, mas ficam explícitas em dois spiders
  alinhados às pastas `brazil/`/`usa/`.
- Evita um único arquivo cheio de `if region` (A) e evita Strategy formal (C)
  sem ganho.
- Escala para CA/MX/UK com mais um adapter fino + config, sem framework.
- Compatível com registry por `allowed_domains` e Proxy Cost Mode.

## Consequências positivas

- Contrato público estável: `store=amazon`, `country` discrimina o mercado.
- Testes separados: comum / BR / US / regressão cross-market.
- Diferenças de pricing condicional isoladas em metadata sem mudar schema.

## Trade-offs / consequências negativas

- Duas classes spider quase idênticas (aceitável; thin wrappers).
- Catálogo interno usa chaves `amazon_br`/`amazon_us` enquanto o campo
  `store` permanece `amazon` — documentado aqui para evitar confusão.
- Markup Amazon muda com frequência; fixtures e fallback de seletores são
  necessários.
