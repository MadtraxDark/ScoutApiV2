# ADR 0021: PostgreSQL no Supabase como fonte de verdade via SQLAlchemy

- Status: Accepted
- Data: 2026-09-14

## Contexto

O ScoutApiV2 já persiste matching e histórico de ofertas em PostgreSQL
(ADR 0019) com SQLAlchemy + Alembic, e usa Redis só como cache/coordenação
(ADR 0020). A operação passa a hospedar o Postgres no **Supabase**, com a
API como único componente autorizado a acessar e gerenciar o banco.

## Problema / decisão necessária

Como integrar o Postgres do Supabase de ponta a ponta sem expor tabelas ao
frontend, sem adotar a Data API (PostgREST) no backend, e sem quebrar o
padrão repository → SQLAlchemy já existente?

## Alternativas consideradas

- **Supabase Data API / PostgREST / supabase-py no backend** — rejeitado:
  duplica regras de negócio, enfraquece o monolito modular e acopla o
  domínio ao vendor HTTP.
- **Acesso direto do frontend ao Postgres/Supabase** — rejeitado: burla
  autorização e contratos da API.
- **ORM alternativo (SQLModel, Prisma, etc.)** — rejeitado: o projeto já
  padroniza SQLAlchemy 2 + Alembic.
- **Conexão direta `DATABASE_URL` + SQLAlchemy/psycopg** — alinhado à
  arquitetura atual e ao Proxy Cost Mode (infra separada do crawl).

## Decisão

1. PostgreSQL (Supabase-hosted ou Compose local) é a **única fonte de
   verdade** de dados de domínio.
2. A API conecta **somente** via `DATABASE_URL` com driver
   `postgresql+psycopg` (SQLAlchemy 2).
3. Evolução de schema **somente** via Alembic (`alembic upgrade head`).
   Preferir conexão direta `:5432` (ou session pooler) para migrations;
   não rodar Alembic no transaction pooler `:6543`.
4. Pooling/timeouts/SSL configuráveis em `core/config.py` /
   `core/database.py`. Hosts Supabase recebem `sslmode=require` por
   padrão; porta `6543` usa `NullPool` + `prepare_threshold=None`.
5. Repositories encapsulam SQLAlchemy; services não embutem SQL cru.
6. Redis permanece fail-open para cache/coordenação — nunca substitui
   persistência.
7. Cliente/frontend fala apenas com a API ScoutApiV2.

## Justificativa

Preserva ADR 0005 (dependency direction), ADR 0019 (matching) e ADR 0020
(Redis não-SoT), com hardening operacional adequado ao Supabase (SSL,
pooler, health).

## Consequências positivas

- Um caminho claro de persistência para agentes e operadores.
- Migrations auditáveis e reprodutíveis no Postgres do Supabase.
- Health check informa estado do banco sem derrubar liveness do Compose.

## Trade-offs / consequências negativas

- Operador precisa escolher URI correta (direct vs pooler).
- IPv6 no endpoint direto pode exigir session pooler ou add-on IPv4.
- `persist=true` / `/offers/refresh` exigem `DATABASE_URL` saudável.

## Relacionado

- ADR 0019, 0020, 0005, 0007
- `docs/persistence/supabase-postgres.md`
- `.cursor/rules/persistence-supabase.mdc`
- `.agents/skills/supabase-postgres/`
