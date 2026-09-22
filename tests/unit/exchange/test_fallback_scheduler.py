"""Fallback / LKG / scheduler tests for exchange refresh."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from scout_api.modules.exchange.domain import FetchedRate, RateType
from scout_api.modules.exchange.refresh_service import refresh_if_due, run_refresh
from scout_api.modules.exchange.schedule import compute_next_refresh_at, is_refresh_due

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


class _OkProvider:
    source_id = "fake_ok"

    def fetch(self) -> list[FetchedRate]:
        return [
            FetchedRate(
                base_currency="USD",
                quote_currency="BRL",
                rate_type=RateType.TOURISM_SELL,
                rate=Decimal("5.30"),
                source=self.source_id,
                source_timestamp=NOW,
                fetched_at=NOW,
            ),
            FetchedRate(
                base_currency="USD",
                quote_currency="BRL",
                rate_type=RateType.TOURISM_BUY,
                rate=Decimal("5.10"),
                source=self.source_id,
                source_timestamp=NOW,
                fetched_at=NOW,
            ),
            FetchedRate(
                base_currency="USD",
                quote_currency="BRL",
                rate_type=RateType.PTAX_SELL,
                rate=Decimal("5.12"),
                source=self.source_id,
                source_timestamp=NOW,
                fetched_at=NOW,
            ),
            FetchedRate(
                base_currency="USD",
                quote_currency="BRL",
                rate_type=RateType.PTAX_BUY,
                rate=Decimal("5.11"),
                source=self.source_id,
                source_timestamp=NOW,
                fetched_at=NOW,
            ),
        ]


class _FailProvider:
    source_id = "fake_fail"

    def fetch(self) -> list[FetchedRate]:
        raise RuntimeError("network down")


class _PygProvider:
    source_id = "fake_pyg"

    def fetch(self) -> list[FetchedRate]:
        return [
            FetchedRate(
                base_currency="PYG",
                quote_currency="BRL",
                rate_type=RateType.OFFICIAL,
                rate=Decimal("0.00086"),
                source=self.source_id,
                source_timestamp=NOW,
                fetched_at=NOW,
            ),
            FetchedRate(
                base_currency="USD",
                quote_currency="PYG",
                rate_type=RateType.OFFICIAL,
                rate=Decimal("5900"),
                source=self.source_id,
                source_timestamp=NOW,
                fetched_at=NOW,
            ),
        ]


def test_scheduler_not_due() -> None:
    future = NOW + timedelta(hours=1)
    assert is_refresh_due(future, now=NOW) is False


def test_scheduler_due_when_past() -> None:
    past = NOW - timedelta(minutes=1)
    assert is_refresh_due(past, now=NOW) is True


def test_scheduler_due_when_none() -> None:
    assert is_refresh_due(None, now=NOW) is True


def test_compute_next_refresh_advances() -> None:
    nxt = compute_next_refresh_at(
        now=NOW, refresh_interval_seconds=1800, jitter_fraction=0.0
    )
    assert nxt == NOW + timedelta(seconds=1800)


def test_primary_fail_secondary_ok(monkeypatch) -> None:
    repo = MagicMock()
    repo.get_last_known_map.return_value = {}
    repo.get_scheduler_state.return_value = None
    monkeypatch.setattr(
        "scout_api.modules.exchange.refresh_service.ExchangeRateRepository",
        lambda _s: repo,
    )
    session = MagicMock()
    summary = run_refresh(
        session,
        valor_provider=_FailProvider(),
        ptax_provider=_OkProvider(),
        bcp_provider=_PygProvider(),
        sml_provider=_FailProvider(),
    )
    assert summary["persisted"] >= 1
    assert any("fake_fail" in e for e in summary["errors"])


def test_all_fail_still_returns_summary(monkeypatch) -> None:
    repo = MagicMock()
    repo.get_last_known_map.return_value = {}
    repo.get_scheduler_state.return_value = None
    monkeypatch.setattr(
        "scout_api.modules.exchange.refresh_service.ExchangeRateRepository",
        lambda _s: repo,
    )
    summary = run_refresh(
        MagicMock(),
        valor_provider=_FailProvider(),
        ptax_provider=_FailProvider(),
        bcp_provider=_FailProvider(),
        sml_provider=_FailProvider(),
    )
    assert summary["persisted"] == 0
    assert summary["fetched"] == 0


def test_refresh_if_due_skips(monkeypatch) -> None:
    state = MagicMock()
    state.next_refresh_at = NOW + timedelta(hours=2)
    repo = MagicMock()
    repo.get_scheduler_state.return_value = state
    monkeypatch.setattr(
        "scout_api.modules.exchange.refresh_service.ExchangeRateRepository",
        lambda _s: repo,
    )
    assert refresh_if_due(MagicMock(), now=NOW) is None
