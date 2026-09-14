# ADR 0019: Product Matching cross-store e histórico de ofertas

- Status: aceito
- Data: 2026-09-14

## Contexto

O ScoutApiV2 já coleta ofertas por URL (`POST /crawl`, `POST /crawl/offer`) com
separação offer/details (ADR 0011), mas não identifica o **mesmo produto** em
lojas diferentes nem mantém histórico para detectar mudanças de preço/seller/
disponibilidade.

A pesquisa técnica (GitHub `product-matcher`, discussions Reddit/SO, paper
Leipzig EDBT 2012) converge em: GTIN validado primeiro; título nunca sozinho
para auto-match; gates de variante (cor/capacidade/tamanho); thresholds
`auto_match` / `review` / `reject`.

## Problema / decisão necessária

Como localizar o mesmo produto nas lojas integradas e atualizar ofertas com
diff sem fabricar matches por similaridade de título nem sobrescrever histórico?

## Alternativas consideradas

- **Somente URLs candidatas fornecidas pelo cliente:** preciso, mas não resolve
  descoberta.
- **Match só contra catálogo interno sem busca ao vivo:** exige ingestão prévia.
- **ML/embeddings/LLM no MVP:** recall bom, custo/latência altos, ainda precisa
  review; overkill.
- **Cascata determinística + busca ao vivo + PostgreSQL:** alinhado ao monolito
  modular e a Proxy Cost Mode.

## Decisão

1. Novo módulo `modules/matching/` (router → service → repository → DB).
2. Descoberta via **busca ao vivo** (`supports_search`) em todas as lojas
   implementadas com adapter SERP (Amazon BR/US, Kabum, Magalu, Shopee,
   Best Buy, Nissei, Shopping China).
3. `MatchingEngine` precision-first: GTIN → brand+model → título auxiliar;
   conflito de variante ou acessório → `reject`; título nunca basta para
   `auto_match`.
4. Persistência PostgreSQL: `CanonicalProduct`, `ProductIdentifier`,
   `StoreListing`, `OfferSnapshot`, `OfferEvent` (Alembic).
5. Endpoints:
   - `POST /match` — referência por URL → search → scrape → score → persist
   - `POST /offers/refresh` — re-scrape + append snapshot/eventos (não overwrite)
6. Reutilizar `ProductScrapeService` / `OfferScrapeService` / HtmlFetcher;
   spiders só adicionam `build_search_url` / `parse_search_results`.

## Justificativa

Minimiza duplicação do crawler, prioriza precisão (requisito explícito), e
materializa o seam do ADR 0008/0011 (`ComparePricesService` / histórico) sem
ML pago.

## Consequências positivas

- Comparação multi-loja com razões explicáveis.
- Histórico append-only para preço/seller/disponibilidade/remoção.
- Search opt-in por loja sem obrigar todas de uma vez.

## Trade-offs / consequências negativas

- SERP é frágil (layout/anti-bot); falha de search ≠ match falso.
- GTIN errado no HTML pode exigir `review` (brand conflict).
- Match multi-loja é caro em fetch; cap de candidatos e Proxy Cost Mode
  obrigatórios na SERP.
- SERPs (especialmente Shopee) podem mudar de markup; parsers são
  store-specific e precisam de manutenção.

## Relacionado

- ADR 0008, 0011, 0014
- `docs/crawler/contracts.md`
- `.cursor/rules/proxy-cost-mode.mdc`
