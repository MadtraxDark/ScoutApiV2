"""Conversion service tests — pure FX, Decimal, original price preserved."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from scout_api.modules.exchange.conversion_service import convert
from scout_api.modules.exchange.domain import RateStatus, RateType
from scout_api.modules.exchange.enrich import attach_conversion


class _FakeRow:
    def __init__(
        self,
        *,
        rate: Decimal,
        rate_type: str = "tourism_sell",
        status: str = "fresh",
        source: str = "valor_data",
        base: str = "USD",
        quote: str = "BRL",
    ) -> None:
        self.rate = rate
        self.rate_type = rate_type
        self.status = status
        self.source = source
        self.base_currency = base
        self.quote_currency = quote
        self.fetched_at = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)
        self.source_timestamp = self.fetched_at
        self.consecutive_failures = 0


def test_usd_conversion_formula_and_rounding(monkeypatch) -> None:
    row = _FakeRow(rate=Decimal("5.3034"))
    repo = MagicMock()
    repo.get_latest.return_value = row
    monkeypatch.setattr(
        "scout_api.modules.exchange.conversion_service.ExchangeRateRepository",
        lambda _session: repo,
    )
    session = MagicMock()
    result = convert(Decimal("999.00"), "USD", session=session)
    assert result.rate == Decimal("5.3034")
    # 999 * 5.3034 = 5298.0966 → R$ 5298.10
    assert result.converted_amount == Decimal("5298.10")
    assert result.rate_type == RateType.TOURISM_SELL
    assert result.rate_status == RateStatus.FRESH
    # Original amount untouched
    assert result.amount == Decimal("999.00")
    assert result.from_currency == "USD"


def test_paraguay_usd_uses_usd_brl_not_cross(monkeypatch) -> None:
    """Paraguay offer in USD must convert USD→BRL directly."""
    row = _FakeRow(rate=Decimal("5.30"))
    repo = MagicMock()
    repo.get_latest.return_value = row
    monkeypatch.setattr(
        "scout_api.modules.exchange.conversion_service.ExchangeRateRepository",
        lambda _session: repo,
    )
    result = convert(Decimal("800"), "USD", session=MagicMock())
    assert result.converted_amount == Decimal("4240.00")
    repo.get_latest.assert_called()
    args = repo.get_latest.call_args[0]
    assert args[0] == "USD"
    assert args[1] == "BRL"


def test_pyg_conversion(monkeypatch) -> None:
    row = _FakeRow(
        rate=Decimal("0.000861"),
        rate_type="official",
        base="PYG",
        source="bcp_referential",
    )
    repo = MagicMock()
    repo.get_latest.return_value = row
    monkeypatch.setattr(
        "scout_api.modules.exchange.conversion_service.ExchangeRateRepository",
        lambda _session: repo,
    )
    result = convert(Decimal("4000000"), "PYG", session=MagicMock())
    assert result.rate_type == RateType.OFFICIAL
    assert result.converted_amount == Decimal("3444.00")


def test_unavailable_when_no_rate(monkeypatch) -> None:
    repo = MagicMock()
    repo.get_latest.return_value = None
    repo.list_latest.return_value = []
    monkeypatch.setattr(
        "scout_api.modules.exchange.conversion_service.ExchangeRateRepository",
        lambda _session: repo,
    )
    result = convert(Decimal("100"), "USD", session=MagicMock())
    assert result.converted_amount is None
    assert result.rate_status == RateStatus.UNAVAILABLE


def test_attach_conversion_empty_for_brl() -> None:
    fields = attach_conversion(Decimal("100"), "BRL", session=MagicMock())
    assert fields["converted_price_brl"] is None


def test_no_tax_in_formula(monkeypatch) -> None:
    """Sanity: convert is exactly amount * rate (no IOF multiplier)."""
    row = _FakeRow(rate=Decimal("5.00"))
    repo = MagicMock()
    repo.get_latest.return_value = row
    monkeypatch.setattr(
        "scout_api.modules.exchange.conversion_service.ExchangeRateRepository",
        lambda _session: repo,
    )
    result = convert(Decimal("1000"), "USD", session=MagicMock())
    assert result.converted_amount == Decimal("5000.00")
