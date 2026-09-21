# Persistência — PostgreSQL no Supabase

A API ScoutApiV2 é o **único** componente que acessa e gerencia o banco.
PostgreSQL (hospedado no Supabase em produção, ou Compose local) é a fonte
de verdade. Redis é apenas cache/coordenação (ADR 0020).

```text
Cliente / Frontend
       ↓
   ScoutApiV2
       ↓
SQLAlchemy / psycopg
       ↓
Supabase PostgreSQL
```

Não use a Supabase Data API / PostgREST para operações do backend.
Não exponha tabelas nem `DATABASE_URL` ao frontend.

Decisão: [ADR 0021](../adr/0021-supabase-postgres-sqlalchemy.md).
Skill do agente: [`.agents/skills/supabase-postgres/`](../../.agents/skills/supabase-postgres/).
Regra Cursor: [`.cursor/rules/persistence-supabase.mdc`](../../.cursor/rules/persistence-supabase.mdc).

## Variáveis de ambiente

| Variável | Função |
|---|---|
| `DATABASE_URL` | URI SQLAlchemy (`postgresql+psycopg://…`) |
| `DATABASE_POOL_SIZE` | Tamanho do QueuePool (ignorado em `:6543`) |
| `DATABASE_MAX_OVERFLOW` | Overflow do pool |
| `DATABASE_POOL_TIMEOUT_SECONDS` | Espera por conexão no pool |
| `DATABASE_POOL_RECYCLE_SECONDS` | Recicla conexões longas |
| `DATABASE_CONNECT_TIMEOUT_SECONDS` | Timeout de handshake TCP |
| `DATABASE_STATEMENT_TIMEOUT_MS` | `statement_timeout` no Postgres |
| `DATABASE_SSLMODE` | Override; Supabase auto-`require` se omitido |
| `DATABASE_APPLICATION_NAME` | `application_name` nas sessões |

Valores de exemplo: [`.env.example`](../../.env.example).

## Setup local (Compose)

1. Copie `.env.example` → `.env`.
2. Escolha o host da `DATABASE_URL` conforme o processo que conecta:
   - **API no Compose** (container):  
     `DATABASE_URL=postgresql+psycopg://scout:scout@postgres:5432/scoutapi`
   - **API no host** (uvicorn local) contra o Postgres publicado:  
     `DATABASE_URL=postgresql+psycopg://scout:scout@localhost:5432/scoutapi`  
   Não use `localhost` dentro do container — aponta para o próprio `api`, não
   para o serviço `postgres`.
3. `docker compose up --build` — o entrypoint aplica `alembic upgrade head`
   automaticamente antes de subir API/workers (`AUTO_MIGRATE=true` por
   padrão; desligue com `AUTO_MIGRATE=false` se um job one-shot já migrou).
4. Manual, se precisar: `docker compose exec api alembic upgrade head`
   (ou `alembic upgrade head` / `make migrate` no host com URL `localhost`).
5. `GET /health` → `database: ok` quando o Postgres responder.
   Se `database: unavailable`, `/match` com `persist=true` (default) responde
   `503 DATABASE_UNAVAILABLE`.

O serviço `postgres` no Compose continua útil para desenvolvimento offline.
Para apontar a API local ao Supabase, substitua só `DATABASE_URL` (e não
commite secrets). Em Docker Desktop (Windows/macOS) redes costumam ser
**só-IPv4**: o host Direct `db.<ref>.supabase.co` frequentemente resolve só
IPv6 e falha com `Network is unreachable` — use o **session pooler** IPv4
(`*.pooler.supabase.com:5432?sslmode=require`).

## Setup produção (Supabase)

1. No Dashboard Supabase → **Connect**, copie a connection string.
2. Prefira **Direct** (`db.<ref>.supabase.co:5432`) para a API long-lived e
   para Alembic **quando a rede tiver IPv6** (ou o Direct também publicar A).
3. Em redes só-IPv4 (inclui muitos ambientes Docker Desktop), use o
   **session pooler** (`…pooler.supabase.com:5432`) — obrigatório se o Direct
   resolver apenas AAAA.
4. Transaction pooler (`:6543`) só se necessário; a API usa `NullPool` e
   desliga prepared statements. **Não** rode Alembic em `:6543`.
5. Force SSL: `?sslmode=require` (ou deixe o auto-append da app).
6. Configure `DATABASE_URL` no secret store / Compose de produção.
7. No Compose/containers ScoutApiV2 o entrypoint já aplica
   `alembic upgrade head` no boot. Em outros deploys, rode no release step
   (ou deixe `AUTO_MIGRATE=true` no entrypoint da imagem).
8. Não habilite políticas que exponham tabelas de matching ao anon key.

## Modelo de produto (ADR 0019)

Não há tabela monolítica `products` misturando preço e identidade. O catálogo
persistido usa:

| Camada | Tabela | Papel |
|---|---|---|
| Identidade | `canonical_products` | Produto canônico (title, brand, model, variant_key, attributes) |
| Identificadores | `product_identifiers` | GTIN/EAN/UPC normalizado (`type`+`value_normalized` único) |
| Oferta/loja | `store_listings` | product_id/SKU/URL por loja (`store`+`canonical_url` único) |
| Preço | `offer_snapshots` | Histórico append-only da oferta |
| Eventos | `offer_events` | Diffs (price/seller/availability/…) |

`ProductOffer` / `ProductDetails` / `ProductPriceItem` do crawler são DTOs de
scraping (Pydantic), não tabelas.

### Deduplicação

Ordem de chaves confiáveis (**título nunca** é chave única):

1. **GTIN/EAN/UPC** em `product_identifiers`
   (`uq_product_identifiers_type_value`)
2. **store + country + product_id** em `store_listings`
   (`uq_store_listings_store_country_product_id`) — identidade típica do spider
   (ASIN Amazon, id KaBuM, skuId Best Buy, etc.)
3. **store + country + sku** (índice único parcial quando `sku` não-vazio)
   (`uq_store_listings_store_country_sku`)
4. **store + canonical_url** (`uq_store_listings_store_url`)

Em corrida, `get_or_create_*` / `upsert_listing` capturam `IntegrityError` e
reutilizam o registro existente (savepoint).

Cadastro explícito: `POST /products` / `GET /products/{id}` via
`ProductRegistrationService`. Matching (`POST /match` + persist) usa as mesmas
chaves no repository.

### Aplicar migrations

```bash
# Containers: automático no boot (docker-entrypoint.sh).
# Host / verificação:
make migrate
# ou
alembic upgrade head
alembic current   # deve mostrar o revision head atual (ex.: 0026_…)
```

Regras:

- Toda criação/evolução de tabela passa por migration.
- Não use `Base.metadata.create_all` em produção (`matching.db.create_all`
  é só bootstrap de teste/dev).
- Autogenerate exige revisão humana do diff.

## Camadas

| Camada | Responsabilidade |
|---|---|
| `core/config.py` | Settings / env |
| `core/database.py` | Engine, pool, SSL, session, health ping, dispose |
| `core/db_errors.py` | Classificação de erros para HTTP |
| `modules/*/models.py` | ORM |
| `modules/*/repository.py` | Queries SQLAlchemy |
| `modules/*/services` | Regras de negócio (sem SQL cru) |
| routers | Traduzem erros de DB para HTTP |

## Lifecycle do Engine

O `Engine` SQLAlchemy é **lazy** e **reutilizado** por processo:

```text
startup (sem connect)
    ↓
primeira necessidade → get_engine() (lru_cache)
    ↓
QueuePool (direct/session) ou NullPool (:6543)
    ↓
Session request-scoped via get_db_session()
    ↓
shutdown (FastAPI lifespan) → dispose_database_engine()
```

Regras:

- Não há conexão forçada no startup só para fechar depois.
- `dispose_database_engine()` é idempotente: se nenhum Engine foi
  cacheado, não cria Engine e não tenta conectar.
- `reset_database_cache()` (testes) chama o mesmo dispose antes de limpar
  os caches — não abandona pools abertos.
- Um processo/worker Python = um Engine = um pool local. Não compartilhe
  Engine entre workers Uvicorn/Gunicorn.

## Dimensionamento do pool

Para direct/session (`QueuePool`), a capacidade aproximada por processo é:

```text
conexões máximas ≈ DATABASE_POOL_SIZE + DATABASE_MAX_OVERFLOW
```

Defaults atuais: `5 + 10 = 15` conexões por processo. Capacidade potencial
total:

```text
workers × réplicas × (pool_size + max_overflow)
```

Em `:6543` (transaction mode) o cliente usa `NullPool`; o limite relevante
é o do Supavisor, não o QueuePool local. Não rode Alembic em `:6543`.

## Health

`GET /health` retorna HTTP 200 com:

```json
{"status": "ok"|"degraded", "database": "ok"|"unavailable"|"not_configured"}
```

Liveness do Compose não depende do Postgres. Trate
`database=unavailable` (com `DATABASE_URL` setada) como não-pronto para
endpoints de persistência.

## Testes

```bash
python -m pytest tests/unit/test_database_connection.py tests/unit/test_matching_repository.py
# opcional, requer Postgres acessível:
TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest -m integration tests/integration/test_postgres_connectivity.py
```
