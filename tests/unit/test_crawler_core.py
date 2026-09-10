from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from scout_api.core.config import Settings
from scout_api.modules.crawler.core.circuit_breaker import CircuitBreaker, CircuitState
from scout_api.modules.crawler.core.exceptions import MissingPriceError
from scout_api.modules.crawler.core.fingerprints import (
    canonicalize_url,
    request_fingerprint,
)
from scout_api.modules.crawler.core.retry import backoff_delay, retry_after
from scout_api.modules.crawler.models.crawl_state import CrawlState
from scout_api.modules.crawler.utils.parsing import parse_money


@pytest.mark.parametrize(
    ("raw", "currency", "expected"),
    [
        ("R$ 4.999,90", "BRL", Decimal("4999.90")),
        ("US$ 899.99", "USD", Decimal("899.99")),
        ("₲ 5.000.000", "PYG", Decimal("5000000")),
    ],
)
def test_parse_money(raw: str, currency: str, expected: Decimal) -> None:
    assert parse_money(raw, currency) == expected


def test_parse_money_rejects_missing_price() -> None:
    with pytest.raises(MissingPriceError):
        parse_money(None, "USD")


def test_fingerprint_removes_tracking() -> None:
    first = canonicalize_url("HTTPS://Example.com/p?a=1&utm_source=x")
    second = canonicalize_url("https://example.com/p?a=1")
    assert first == second
    assert request_fingerprint("x", first, "sku") == request_fingerprint(
        "x", second, "sku"
    )


def test_retry_and_circuit_breaker() -> None:
    assert 0 <= backoff_delay(3, base=1, cap=4) <= 4
    assert retry_after("2") == 2
    breaker = CircuitBreaker(threshold=2, cooldown=10)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert not breaker.allow()
    assert breaker.allow(datetime.now(UTC) + timedelta(seconds=11))


def test_state_due_and_schedule() -> None:
    state = CrawlState(store="x", product_id="1")
    assert state.due()
    state.schedule(100)
    assert not state.due()


def test_legacy_release_debug_setting_is_production_mode() -> None:
    assert Settings(debug="release").debug is False
