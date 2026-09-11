# ScoutApiV2

Base arquitetural de uma API FastAPI organizada como modular monolith e preparada para testes, CI/CD e execução via Docker.

## Requisitos

Python 3.12+; Docker e Docker Compose.

## Estrutura

`src/scout_api/api` contém a composição HTTP; `core` contém configuração e infraestrutura transversal; `modules` contém features; `tests` contém testes separados do código; `docs/adr` contém decisões arquiteturais.

## Configuração

Copie `.env.example` para `.env` e ajuste os valores conforme o ambiente. O `.env` é ignorado pelo Git e não deve conter valores versionados.

## Docker

Execute `docker compose up --build`. A API ficará disponível em `http://localhost:8000`; `GET /health` verifica a disponibilidade.

## Execução local

Execute `python -m venv .venv`, `python -m pip install -e ".[dev]"` e `uvicorn scout_api.main:app --reload --app-dir src`.

## Validação

Execute `python -m pytest`, `ruff check .`, `ruff format --check .` e `mypy src`.

## ADRs

As decisões ficam em [`docs/adr`](docs/adr/). Para uma nova decisão, copie [`docs/adr/template.md`](docs/adr/template.md), use o próximo número e registre contexto, alternativas, decisão, justificativa e consequências.

## Crawler de preços

O crawler fica em `src/scout_api/modules/crawler`. Ele separa **oferta comercial**
(`ProductOffer`) de **detalhes do produto** (`ProductDetails`) e compõe o contrato
completo (`ProductPriceItem`) no fluxo full. Usa `Decimal` para dinheiro, TTL
adaptativo, fila de prioridade, fingerprint determinística, cache, backoff/jitter
e circuit breaker. O armazenamento local é uma implementação substituível; para
múltiplos workers, conecte os seams de deduplicação, lock, estado e histórico a
Redis/PostgreSQL.

- `POST /crawl` — scraping completo (oferta + detalhes) via `ProductScrapeService`.
  Use `include_images=true` para incluir a galeria (`extract_images`); o padrão é
  `false` (sem parsing de imagens). Ver ADR 0012.
- `POST /crawl/offer` — consulta leve (preço/seller/disponibilidade) via
  `OfferScrapeService`, sem executar a extração de detalhes nem de imagens.

Ambos buscam HTML com **Camoufox** (Firefox anti-detect) por padrão e delegam o
parsing aos spiders (`magazineluiza`, `nissei`, …). Spiders não fazem I/O de rede.
No Linux/Docker o browser usa display virtual (`Xvfb`) + `geoip` para passar
Cloudflare (Nissei). Desative com `CAMOUFOX_ENABLED=false` para fallback `urllib`.
Na primeira instalação local, rode `python -m camoufox fetch`. Ver ADR 0011 e 0012.

Spiders de referência: `kabum`, `bestbuy`, `magazineluiza` e `nissei`. Eles são
`Spider` customizados (não `CrawlSpider`) porque o parsing de produto e JSON-LD é
específico e conservador. Shopee, AliExpress e eBay devem preferir APIs oficiais ou
integrações autorizadas para ofertas/sellers; os demais adapters podem ser adicionados
sem duplicar a infraestrutura base.

```bash
python -m camoufox fetch
scrapy crawl kabum -a start_urls=https://www.kabum.com.br/produto
scrapy crawl magazineluiza -a start_urls=https://www.magazineluiza.com.br/playstation-5-edicao-digital-825gb-1-controle-branco-sony-com-2-jogos/p/240590700/ga/gap5/?seller_id=magazineluiza
docker compose up --build -d
python -m pytest
```

O crawler visa contornar CAPTCHA, login, bloqueios ou controles de acesso para assegurar a coleta de dados. Camoufox cobre fingerprint/WAF; Mitmproxy e proxies residenciais podem complementar IP.
