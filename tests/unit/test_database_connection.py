"""Unit tests for PostgreSQL / Supabase connection helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.pool import NullPool, QueuePool

from scout_api.core.config import Settings
from scout_api.core.database import (
    build_connect_args,
    check_database,
    create_db_engine,
    ensure_sslmode,
    is_supabase_host,
    is_transaction_pooler,
    normalize_database_url,
    reset_database_cache,
)
from scout_api.core.db_errors import classify_database_error


@pytest.fixture(autouse=True)
def _clear_engine_cache() -> None:
    reset_database_cache()
    yield
    reset_database_cache()


def test_normalize_database_url_postgres_scheme() -> None:
    assert (
        normalize_database_url("postgres://u:p@host:5432/db")
        == "postgresql+psycopg://u:p@host:5432/db"
    )


def test_normalize_database_url_keeps_psycopg() -> None:
    url = "postgresql+psycopg://u:p@host:5432/db"
    assert normalize_database_url(url) == url


def test_ensure_sslmode_for_supabase_host() -> None:
    url = "postgresql+psycopg://postgres.abc:secret@db.abc.supabase.co:5432/postgres"
    secured = ensure_sslmode(url, default_sslmode=None)
    assert "sslmode=require" in secured


def test_ensure_sslmode_respects_explicit() -> None:
    url = (
        "postgresql+psycopg://postgres.abc:secret@db.abc.supabase.co:5432/"
        "postgres?sslmode=verify-full"
    )
    assert ensure_sslmode(url, default_sslmode="require") == url


def test_is_supabase_and_transaction_pooler() -> None:
    tx = (
        "postgresql+psycopg://postgres.abc:x@aws-0-us-east-1.pooler.supabase.com:"
        "6543/postgres"
    )
    direct = "postgresql+psycopg://postgres:x@db.abc.supabase.co:5432/postgres"
    assert is_supabase_host(tx)
    assert is_transaction_pooler(tx)
    assert is_supabase_host(direct)
    assert not is_transaction_pooler(direct)


def test_build_connect_args_disables_prepared_on_tx_pooler() -> None:
    settings = Settings(
        database_url=(
            "postgresql+psycopg://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        ),
        database_statement_timeout_ms=1000,
        database_application_name="scout-test",
    )
    args = build_connect_args(settings, settings.database_url or "")
    assert args["prepare_threshold"] is None
    assert "statement_timeout=1000" in args["options"]
    assert "application_name=scout-test" in args["options"]


def test_create_db_engine_uses_null_pool_for_transaction_mode() -> None:
    settings = Settings(
        database_url=(
            "postgresql+psycopg://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        )
    )
    engine = create_db_engine(settings)
    assert isinstance(engine.pool, NullPool)
    engine.dispose()


def test_create_db_engine_uses_queue_pool_for_direct() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://scout:scout@localhost:5432/scoutapi",
        database_pool_size=3,
        database_max_overflow=1,
    )
    engine = create_db_engine(settings)
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.size() == 3
    engine.dispose()


def test_check_database_not_configured() -> None:
    with patch("scout_api.core.database.get_settings") as mock_settings:
        mock_settings.return_value = Settings(database_url=None)
        assert check_database() == "not_configured"


def test_check_database_unavailable() -> None:
    with (
        patch("scout_api.core.database.get_settings") as mock_settings,
        patch(
            "scout_api.core.database.ping_database",
            side_effect=OperationalError("stmt", {}, Exception("down")),
        ),
    ):
        mock_settings.return_value = Settings(
            database_url="postgresql+psycopg://u:p@localhost:5432/db"
        )
        assert check_database() == "unavailable"


def test_classify_database_error_operational() -> None:
    failure = classify_database_error(
        OperationalError("SELECT 1", {}, Exception("timeout"))
    )
    assert failure.code == "DATABASE_UNAVAILABLE"
    assert failure.retryable is True


def test_classify_database_error_integrity() -> None:
    failure = classify_database_error(IntegrityError("INSERT", {}, Exception("unique")))
    assert failure.code == "DATABASE_INTEGRITY_ERROR"
    assert failure.retryable is False


def test_classify_unknown_exception() -> None:
    failure = classify_database_error(RuntimeError("boom"))
    assert failure.code == "DATABASE_ERROR"
