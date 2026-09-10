# ADR 0009: Fetch de produto via Camoufox

- Status: Accepted
- Data: 2026-09-10

## Contexto

Lojas como Magazine Luiza (Akamai) e Nissei (Cloudflare) bloqueiam o fetch HTTP
simples (`urllib`) usado pelo `ProductScrapeService`. Probes com Playwright,
Botasaurus e CloakBrowser falharam; Camoufox (Firefox com patches em C++)
conseguiu HTML de produto utilizável pelos spiders existentes.

## Problema / decisão necessária

Como obter HTML de produto sem reescrever os spiders de parsing?

## Alternativas consideradas

- Manter apenas `urllib` / Scrapy downloader
- camofox-browser (servidor Node + REST em cima do Camoufox)
- Camoufox via Python no próprio service de fetch
- Proxy residencial como única mitigação

## Decisão

Usar Camoufox via Python como fetcher padrão do `ProductScrapeService`.
Os spiders continuam recebendo `HtmlResponse` e só fazem parsing. `urllib`
permanece disponível quando `CAMOUFOX_ENABLED=false` (testes / lojas leves).

## Justificativa

Camoufox é o motor que já validamos; a API Python evita processo Node extra e
encaixa no monólito. Separar fetch de parse preserva a direção
router → service → spider.

## Consequências positivas

- Magalu e Nissei passam a ter caminho de coleta viável no mesmo contrato HTTP
- Spiders e fixtures de parsing permanecem testáveis sem browser
- Configuração centralizada (`CAMOUFOX_*`) e fetcher injetável

## Trade-offs / consequências negativas

- Imagem Docker maior (binário Camoufox + libs GUI)
- Fetch mais lento e mais RAM que HTTP puro
- Em datacenter ainda pode falhar; proxy residencial continua opção complementar
