---
name: supabase-postgres
description: >-
  Persistência ScoutApiV2 com PostgreSQL no Supabase via SQLAlchemy/psycopg e
  Alembic. Use ao alterar DATABASE_URL, models ORM, repositories, migrations,
  health de banco, pooling/SSL, ou integração Supabase. Nunca use Data API.
---

# Supabase / PostgreSQL (ScoutApiV2)

## Escopo aprovado

- Conexão direta `DATABASE_URL` → SQLAlchemy 2 + `psycopg`
- Models / repositories / Alembic
- Pooling, SSL, timeouts, health, erros de DB
- Docs de setup local/produção

## Fora de escopo

- Supabase Data API / PostgREST / `supabase-py` no backend
- Acesso do frontend ao Postgres
- Trocar Redis por persistência
- Alterar fetch/Camoufox

## Precedência

Tarefa explícita → `AGENTS.md` → ADR 0021 → `.cursor/rules/persistence-supabase.mdc`
→ código atual → esta skill.

## Fluxo obrigatório para mudanças de schema

1. Atualizar ORM em `modules/*/models.py` (herda `core.database.Base`).
2. Gerar migration: `alembic revision --autogenerate -m "slug"`.
3. Revisar o arquivo em `alembic/versions/` (não aceitar autogenerate cego).
4. Aplicar: `alembic upgrade head` (URI direct/session `:5432`, nunca `:6543`).
5. Ajustar repository (SQLAlchemy); **sem SQL cru em services**.
6. Testes unitários (repository/fakes) + integração se `TEST_DATABASE_URL`.
7. Atualizar `docs/persistence/supabase-postgres.md` se o contrato operacional mudou.

## Conexão

- Normalizar para `postgresql+psycopg://…`
- Hosts Supabase: `sslmode=require` (auto se omitido)
- `:6543` (transaction pooler): `NullPool` + `prepare_threshold=None`
- Demais: QueuePool com settings `DATABASE_POOL_*`
- Redis = cache only

## Erros

Usar `core.db_errors.classify_database_error`; routers mapeiam para HTTP
(`503` unavailable, `409` integrity, `500` demais) sem vazar SQL/secrets.

## Referências

- ADR 0021, ADR 0019, ADR 0020
- `src/scout_api/core/database.py`
- `docs/persistence/supabase-postgres.md`
