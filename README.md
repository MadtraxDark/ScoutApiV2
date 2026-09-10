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

O crawler fica em `src/scout_api/modules/crawler`. Ele usa um modelo normalizado de
oferta (`ProductPriceItem`), `Decimal` para dinheiro, TTL adaptativo, fila de
prioridade, fingerprint determinística, cache, backoff/jitter e circuit breaker.
O armazenamento local é uma implementação substituível; para múltiplos workers,
conecte os seams de deduplicação, lock, estado e histórico a Redis/PostgreSQL.

Spiders de referência implementados: `kabum`, `bestbuy` e `nissei`. Eles são
`Spider` customizados (não `CrawlSpider`) porque o parsing de produto e JSON-LD é
específico e conservador. Shopee, AliExpress e eBay devem preferir APIs oficiais ou
integrações autorizadas para ofertas/sellers; os demais adapters podem ser adicionados
sem duplicar a infraestrutura base.

```bash
scrapy crawl kabum -a start_urls=https://www.kabum.com.br/produto
docker compose up --build -d
python -m pytest
```

O crawler obedece `robots.txt`, usa concorrência conservadora e não contorna CAPTCHA,
login, bloqueios ou controles de acesso. Mitmproxy e proxies são opcionais e destinados
somente a ambientes autorizados de diagnóstico.
