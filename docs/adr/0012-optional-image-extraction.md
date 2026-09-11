# ADR 0012: Extração opcional de imagens no fluxo completo

- Status: aceito
- Data: 2026-09-10

## Contexto

O ADR 0011 separou **Product Offer** e **Product Details**, com `ProductScrapeService`
compondo oferta + detalhes em `POST /crawl` e `OfferScrapeService` expondo
`POST /crawl/offer`. Imagens já existiam em `ProductDetails.images`, mas a
extração da galeria ainda podia ser acoplada a `extract_details()` ou omitida
sem um controle explícito de custo.

A galeria de produto é um nível de custo adicional (parsing e payload) que
muitos consumidores de preço/identidade não precisam.

## Problema / decisão necessária

Como permitir scraping **com ou sem** galeria de imagens no mesmo fluxo
completo, sem duplicar scrapers, sem múltiplos fetches da mesma página e sem
contaminar `POST /crawl/offer`?

## Alternativas consideradas

- **Dois scrapers completos (com/sem imagens):** duplica adapters, fetch e
  orquestração.
- **Sempre extrair imagens em `extract_details()`:** força custo de parsing
  mesmo quando o consumidor não precisa da galeria.
- **Flag `include_images` + `extract_images()` no adapter, orquestrado pelo
  serviço:** reutiliza o mesmo HTML/fetch e mantém responsabilidades
  separadas.

## Decisão

Estender a arquitetura do ADR 0011 com um terceiro extractor opcional:

1. `CrawlRequest.include_images: bool = False` (padrão evita custo desnecessário).
2. Adapters (`BaseStoreSpider`) expõem:
   - `extract_offer()`
   - `extract_details()` — **sem** processar galeria
   - `extract_images()` — somente quando solicitado
3. `ProductScrapeService.scrape(url, *, include_images=False)` orquestra:
   - `extract_offer()`
   - `extract_details()`
   - `extract_images()` **somente se** `include_images=True`
4. Uma única resposta HTML alimenta todos os extractors da operação.
5. `ProductDetails.images` (e o contrato completo `ProductPriceItem.images`)
   permanece vazio quando `include_images=False`.
6. `POST /crawl/offer` **nunca** chama `extract_images()`.

Níveis de custo conceituais:

```text
Offer                  → preço / Pix / parcelamento / seller / disponibilidade
Product                → Offer + identidade / descrição / specs
Product + Images       → Product + galeria normalizada
```

## Justificativa

A flag explícita deixa o custo da galeria opt-in sem criar um segundo crawler.
Separar `extract_images()` impede que `extract_details()` pague o parsing da
galeria no caminho default. Compatibilidade: `/crawl` continua funcionando sem
imagens; `/crawl/offer` permanece comercial-only.

## Consequências positivas

- Consumidores de preço/identidade não pagam parsing de galeria por padrão.
- Mesmo adapter e mesmo fetch cobrem os três níveis de custo.
- Testes podem provar que `extract_images()` não é chamado nos caminhos default.

## Trade-offs / consequências negativas

- Resultado em cache sem imagens pode não satisfazer um pedido posterior com
  `include_images=true` até o TTL expirar (mesmo URL/cooldown).
- Mais um método por adapter e um campo no request/contrato completo para
  documentar.
