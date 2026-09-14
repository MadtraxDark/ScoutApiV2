"""SQLAlchemy engine and session helpers for domain persistence."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from scout_api.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Defina a URL PostgreSQL para "
            "persistência de matching/ofertas."
        )
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_database_cache() -> None:
    """Clear cached engine/session factory (tests)."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
