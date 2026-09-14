"""Unit tests for distributed URL/domain cooldown."""

from __future__ import annotations

import pytest
from tests.unit.fakes.fake_redis import FakeRedis

from scout_api.modules.crawler.core.distributed_cooldown import DistributedCooldown
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.core.redis_client import RedisGateway
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard


def _gateway(fake: FakeRedis) -> RedisGateway:
    return RedisGateway("redis://localhost:6379/0", client=fake)


def test_url_cooldown_second_request_duplicate() -> None:
    fake = FakeRedis()
    cooldown = DistributedCooldown(_gateway(fake))
    first = cooldown.try_acquire(
        "https://nissei.com/py/a",
        "nissei.com",
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
    )
    assert first.allowed is True
    second = cooldown.try_acquire(
        "https://nissei.com/py/a",
        "nissei.com",
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
    )
    assert second.allowed is False
    assert second.code == "DUPLICATE_REQUEST"
    assert second.retry_after is not None and second.retry_after >= 1


def test_domain_cooldown_blocks_other_url_same_host() -> None:
    fake = FakeRedis()
    cooldown = DistributedCooldown(_gateway(fake))
    assert cooldown.try_acquire(
        "https://nissei.com/py/a",
        "nissei.com",
        url_cooldown_seconds=1,
        domain_min_interval_seconds=30,
    ).allowed
    blocked = cooldown.try_acquire(
        "https://nissei.com/py/b",
        "nissei.com",
        url_cooldown_seconds=1,
        domain_min_interval_seconds=30,
    )
    assert blocked.allowed is False
    assert blocked.code == "RATE_LIMITED"


def test_other_domain_allowed() -> None:
    fake = FakeRedis()
    cooldown = DistributedCooldown(_gateway(fake))
    assert cooldown.try_acquire(
        "https://amazon.com/dp/1",
        "amazon.com",
        url_cooldown_seconds=60,
        domain_min_interval_seconds=30,
    ).allowed
    assert cooldown.try_acquire(
        "https://magazineluiza.com.br/p/1",
        "magazineluiza.com.br",
        url_cooldown_seconds=60,
        domain_min_interval_seconds=30,
    ).allowed


def test_two_guards_share_redis_cooldown() -> None:
    fake = FakeRedis()
    gateway = _gateway(fake)
    cooldown = DistributedCooldown(gateway)
    guard_a = ScrapeGuard(
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
        distributed_cooldown=cooldown,
        distributed_cooldown_enabled=True,
    )
    guard_b = ScrapeGuard(
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
        distributed_cooldown=cooldown,
        distributed_cooldown_enabled=True,
    )
    url = "https://nissei.com/py/shared"
    guard_a.acquire_for_live_fetch(url)
    with pytest.raises(RequestError) as exc:
        guard_b.acquire_for_live_fetch(url)
    assert exc.value.code == "DUPLICATE_REQUEST"


def test_redis_unavailable_falls_back_to_local() -> None:
    fake = FakeRedis()
    gateway = _gateway(fake)
    cooldown = DistributedCooldown(gateway)
    guard = ScrapeGuard(
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
        distributed_cooldown=cooldown,
        distributed_cooldown_enabled=True,
    )
    fake.fail_next = True
    url = "https://nissei.com/py/local-fallback"
    # First call: redis fails → local acquire OK
    guard.acquire_for_live_fetch(url)
    # Second call: redis still usable after fail_next cleared; local also blocks.
    # Force redis fail again so only local matters.
    fake.fail_next = True
    with pytest.raises(RequestError) as exc:
        guard.acquire_for_live_fetch(url)
    assert exc.value.code == "DUPLICATE_REQUEST"
