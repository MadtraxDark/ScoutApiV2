"""Optional Redis integration tests (skipped when Redis is unavailable)."""

from __future__ import annotations

import os
import threading
import time
from decimal import Decimal

import pytest
from redis import Redis
from redis.exceptions import RedisError

from scout_api.modules.crawler.core.cache import ResponseCache, build_cache_backend
from scout_api.modules.crawler.core.distributed_cooldown import DistributedCooldown
from scout_api.modules.crawler.core.distributed_single_flight import (
    DistributedSingleFlight,
)
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.core.redis_client import RedisGateway
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.models.product import ProductPriceItem

pytestmark = pytest.mark.integration


def _redis_url() -> str:
    return (os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/15").strip()


@pytest.fixture(scope="module")
def redis_gateway() -> RedisGateway:
    url = _redis_url()
    try:
        client = Redis.from_url(
            url,
            decode_responses=False,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        client.flushdb()
    except RedisError as exc:
        pytest.skip(f"Redis unavailable for integration tests: {exc}")
    gateway = RedisGateway(url, connect_timeout=0.5, socket_timeout=0.5, client=client)
    yield gateway
    try:
        client.flushdb()
        client.close()
    except RedisError:
        pass


def _item(url: str) -> ProductPriceItem:
    return ProductPriceItem(
        store="nissei",
        country="PY",
        product_id="1",
        title="Produto",
        url=url,
        canonical_url=url,
        currency="PYG",
        price=Decimal("1000"),
    )


def test_process_a_writes_process_b_reads(redis_gateway: RedisGateway) -> None:
    cache_a = ResponseCache(backend=build_cache_backend(redis_gateway=redis_gateway))
    cache_b = ResponseCache(backend=build_cache_backend(redis_gateway=redis_gateway))
    guard_a = ScrapeGuard(result_cache_ttl_seconds=60, cache=cache_a)
    guard_b = ScrapeGuard(result_cache_ttl_seconds=60, cache=cache_b)
    url = "https://nissei.com/py/integration-cache"
    guard_a.store_success(url, _item(url))
    cached = guard_b.get_cached(url)
    assert cached is not None
    assert cached.metadata.get("served_from") == "redis"


def test_lock_and_wait_between_guards(redis_gateway: RedisGateway) -> None:
    flight = DistributedSingleFlight(
        redis_gateway,
        lock_ttl_seconds=30,
        wait_seconds=3,
        poll_min_seconds=0.02,
        poll_max_seconds=0.05,
    )
    cache = ResponseCache(backend=build_cache_backend(redis_gateway=redis_gateway))
    guard = ScrapeGuard(
        result_cache_ttl_seconds=60,
        cache=cache,
        distributed_flight=flight,
        distributed_lock_enabled=True,
        url_cooldown_seconds=0,
        domain_min_interval_seconds=0,
    )
    url = "https://nissei.com/py/integration-flight"
    calls: list[str] = []
    barrier = threading.Barrier(2)
    results: list[ProductPriceItem] = []

    def leader() -> None:
        barrier.wait(timeout=2)

        def _fn() -> ProductPriceItem:
            calls.append("live")
            time.sleep(0.2)
            item = _item(url)
            guard.store_success(url, item)
            return item

        results.append(guard.run_coalesced(url, _fn, result_kind="product"))

    def follower() -> None:
        barrier.wait(timeout=2)
        time.sleep(0.05)

        def _fn() -> ProductPriceItem:
            calls.append("follower-live")
            return _item(url)

        results.append(guard.run_coalesced(url, _fn, result_kind="product"))

    threads = [threading.Thread(target=leader), threading.Thread(target=follower)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert len(results) == 2
    assert calls == ["live"]


def test_shared_cooldown(redis_gateway: RedisGateway) -> None:
    cooldown = DistributedCooldown(redis_gateway)
    guard_a = ScrapeGuard(
        url_cooldown_seconds=30,
        domain_min_interval_seconds=0,
        distributed_cooldown=cooldown,
        distributed_cooldown_enabled=True,
    )
    guard_b = ScrapeGuard(
        url_cooldown_seconds=30,
        domain_min_interval_seconds=0,
        distributed_cooldown=cooldown,
        distributed_cooldown_enabled=True,
    )
    url = "https://nissei.com/py/integration-cooldown"
    guard_a.acquire_for_live_fetch(url)
    with pytest.raises(RequestError) as exc:
        guard_b.acquire_for_live_fetch(url)
    assert exc.value.code == "DUPLICATE_REQUEST"


def test_api_continues_when_gateway_broken() -> None:
    """Fail-open: broken injected client does not prevent local scrape guard use."""
    from tests.unit.fakes.fake_redis import FakeRedis

    fake = FakeRedis()
    gateway = RedisGateway("redis://localhost:6379/0", client=fake)
    fake.fail_next = True
    guard = ScrapeGuard(
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
        result_cache_ttl_seconds=60,
        cache=ResponseCache(backend=build_cache_backend(redis_gateway=gateway)),
        distributed_flight=DistributedSingleFlight(gateway, wait_seconds=0.2),
        distributed_cooldown=DistributedCooldown(gateway),
        distributed_lock_enabled=True,
        distributed_cooldown_enabled=True,
    )
    url = "https://nissei.com/py/integration-failopen"
    guard.store_success(url, _item(url))
    assert guard.get_cached(url) is not None
