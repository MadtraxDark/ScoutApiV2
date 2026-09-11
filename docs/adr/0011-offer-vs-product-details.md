# ADR 0011: Separação entre Product Offer e Product Details

- Status: aceito
- Data: 2026-09-10

## Contexto

O crawler expõe `POST /crawl` através do `ProductScrapeService`, que busca a página,
executa o parser da loja e devolve um `ProductPriceItem` completo (identidade,
detalhes comerciais, metadados). Clientes que só precisam de preço, seller e
disponibilidade pagam semanticamente o mesmo pipeline de extração completa.

O custo de fetch (especialmente Camoufox) pode continuar sendo o maior fator de
latência; mesmo assim, a arquitetura não deve obrigar a consulta comercial a
executar parsing de detalhes irrelevantes para comparação de preço.

## Problema / decisão necessária

Como separar explicitamente:

- consulta leve de oferta (preço / disponibilidade / seller);
- scraping completo do produto (oferta + detalhes);

sem quebrar `POST /crawl`, sem duplicar crawlers por loja e sem hardcode de loja
na camada de serviço?

## Alternativas consideradas

- **Manter um único fluxo `ProductScrapeService` + flags de “campos opcionais”:**
  continua acoplado; difícil garantir que detalhes não sejam parseados.
- **Dois scrapers independentes por loja (offer crawler vs details crawler):**
  duplica fetch helpers, resolução de seller e parsing monetário.
- **Separar modelos e extractors no adapter (`extract_offer` / `extract_details`)
  com serviços dedicados e endpoint leve:** reutiliza fetch/guard/spiders e deixa
  o fluxo completo como composição.

## Decisão

Adotar a separação **Product Offer** vs **Product Details**:

1. Modelos `ProductOffer` e `ProductDetails`, mantendo `ProductPriceItem` como
   contrato público do fluxo completo.
2. `BaseStoreSpider` evolui com `extract_offer()` e `extract_details()`;
   `parse_product()` compõe os dois no item completo.
3. Serviços:
   - `OfferScrapeService` — somente oferta;
   - `ProductDetailsService` — somente detalhes;
   - `ProductScrapeService` — orquestra oferta + detalhes (compatível com
     `POST /crawl`).
4. Novo endpoint `POST /crawl/offer` retorna apenas `ProductOffer`.
5. Resolução de loja permanece compartilhada (sem hardcode Magalu no serviço).
6. Magazine Luiza é a primeira loja com extração de oferta realmente separada
   da de detalhes.

A extração opcional de imagens (`include_images` / `extract_images`) é definida
no ADR 0012 e estende este contrato sem alterar a separação offer/details.

## Justificativa

A comparação entre lojas precisa de um contrato comercial estável e barato de
processar após o HTML (ou, no futuro, após uma fonte mais leve). Detalhes
catalográficos (descrição, imagens, specs) não devem contaminar esse caminho.
Compor `ProductPriceItem` a partir de oferta + detalhes preserva compatibilidade
e evita dois crawlers paralelos.

## Consequências positivas

- Clientes de preço usam `POST /crawl/offer` sem depender do modelo completo.
- Adapters podem otimizar `extract_offer()` sem alterar o contrato de `/crawl`.
- Futuras estratégias de fetch por loja (API comercial → JSON → HTML → Camoufox)
  podem ser injetadas no `OfferScrapeService` sem redesenhar o monolito.
- Base pronta para um futuro `ComparePricesService` sem implementá-lo agora.

## Trade-offs / consequências negativas

- Separar extractors **não elimina** o custo de fetch quando Camoufox for
  obrigatório; a latência de rede/browser pode continuar dominante.
- Lojas ainda não refatoradas podem projetar oferta a partir do parse legado
  até migrarem de fato.
- Há mais tipos e endpoints para documentar e testar.
