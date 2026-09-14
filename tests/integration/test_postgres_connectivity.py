"""Optional PostgreSQL / Supabase connectivity integration tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from scout_api.core.config import Settings
from scout_api.core.database import create_db_engine, ping_database

pytestmark = pytest.mark.integration


def _database_url() -> str | None:
    return (
        os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    ).strip() or None


@pytest.fixture(scope="module")
def pg_settings() -> Settings:
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL / TEST_DATABASE_URL não configurada")
    return Settings(database_url=url)


def test_postgres_ping_and_select(pg_settings: Settings) -> None:
    engine = create_db_engine(pg_settings)
    try:
        ping_database(engine)
        with engine.connect() as conn:
            value = conn.execute(text("SELECT 1")).scalar_one()
        assert value == 1
    finally:
        engine.dispose()
