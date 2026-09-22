from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from scout_api.core.config import get_settings
from scout_api.core.database import (
    Base,
    build_connect_args,
    ensure_sslmode,
    normalize_database_url,
    resolve_engine_url,
)
from scout_api.modules.matching import models as matching_models  # noqa: F401
from scout_api.modules.exchange import models as exchange_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Resolve DATABASE_URL; prefer direct/session Postgres for migrations.

    Do not run Alembic against Supabase transaction pooler (:6543). Use the
    direct ``db.<ref>.supabase.co:5432`` URI or session-mode pooler (:5432).
    """
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required to run Alembic migrations")
    return settings.database_url


def run_migrations_offline() -> None:
    settings = get_settings()
    url = ensure_sslmode(
        normalize_database_url(get_url()),
        default_sslmode=settings.database_sslmode,
    )
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # One-shot migration process: always NullPool (never share app QueuePool).
    # Prefer direct :5432 or session pooler — not transaction :6543.
    settings = get_settings()
    url = resolve_engine_url(settings)
    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
        future=True,
        connect_args=build_connect_args(settings, url),
    )
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
