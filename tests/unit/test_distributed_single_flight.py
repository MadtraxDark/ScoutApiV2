"""Unit tests for distributed single-flight coordination."""

from __future__ import annotations

import threading
import time
from decimal import Decimal

from tests.unit.fakes.fake_redis import FakeRedis

from scout_api.modules.crawler.core.cache import ResponseCache, build_cache_backend
from scout_api.modules.crawler.core.distributed_single_flight import (
    DistributedSingleFlight,
)
from scout_api.modules.crawler.core.redis_client import RedisGateway
from scout_api.modules.crawler.core.redis_keys import flight_lock_key
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.models.product import ProductPriceItem


def _gateway(fake: FakeRedis) -> RedisGateway:
    return RedisGateway("redis://localhost:6379/0", client=fake)


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


def test_leader_acquires_lock_follower_waits_for_cache() -> None:
    fake = FakeRedis()
    gateway = _gateway(fake)
    flight = DistributedSingleFlight(
        gateway,
        lock_ttl_seconds=30,
        wait_seconds=2.0,
        poll_min_seconds=0.01,
        poll_max_seconds=0.02,
    )
    cache = ResponseCache(backend=build_cache_backend(redis_gateway=gateway))
    # Separate local SingleFlight instances simulate two API processes.
    from scout_api.modules.crawler.core.single_flight import SingleFlight

    guard_a = ScrapeGuard(
        result_cache_ttl_seconds=60,
        cache=cache,
        single_flight=SingleFlight(),
        distributed_flight=flight,
        distributed_lock_enabled=True,
        distributed_cooldown_enabled=False,
        url_cooldown_seconds=0,
        domain_min_interval_seconds=0,
    )
    guard_b = ScrapeGuard(
        result_cache_ttl_seconds=60,
        cache=cache,
        single_flight=SingleFlight(),
        distributed_flight=flight,
        distributed_lock_enabled=True,
        distributed_cooldown_enabled=False,
        url_cooldown_seconds=0,
        domain_min_interval_seconds=0,
    )
    url = "https://nissei.com/py/flight-a"
    calls: list[str] = []
    barrier = threading.Barrier(2)
    results: list[ProductPriceItem] = []
    errors: list[BaseException] = []

    def leader() -> None:
        try:
            barrier.wait(timeout=2)

            def _fn() -> ProductPriceItem:
                calls.append("leader")
                time.sleep(0.15)
                item = _item(url)
                guard_a.store_success(url, item)
                return item

            results.append(guard_a.run_coalesced(url, _fn, result_kind="product"))
        except BaseException as exc:  # noqa: BLE001 — collect for assertion
            errors.append(exc)

    def follower() -> None:
        try:
            barrier.wait(timeout=2)
            time.sleep(0.02)

            def _fn() -> ProductPriceItem:
                calls.append("follower-fn")
                return _item(url)

            results.append(guard_b.run_coalesced(url, _fn, result_kind="product"))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=leader), threading.Thread(target=follower)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    assert len(results) == 2
    assert calls.count("leader") == 1
    assert "follower-fn" not in calls


def test_lock_has_ttl_and_owner_only_release() -> None:
    fake = FakeRedis()
    flight = DistributedSingleFlight(_gateway(fake), lock_ttl_seconds=2)
    url = "https://nissei.com/py/lock-ttl"
    acquired = flight.try_acquire(url)
    assert acquired.token is not None
    key = flight_lock_key(url)
    assert fake.get(key) is not None
    # Foreign token cannot delete
    flight.release(url, "not-the-owner")
    assert fake.get(key) is not None
    flight.release(url, acquired.token)
    assert fake.get(key) is None


def test_owner_crash_lock_expires() -> None:
    fake = FakeRedis()
    flight = DistributedSingleFlight(_gateway(fake), lock_ttl_seconds=1)
    url = "https://nissei.com/py/lock-expire"
    acquired = flight.try_acquire(url)
    assert acquired.token is not None
    time.sleep(1.05)
    stolen = flight.try_acquire(url)
    assert stolen.token is not None
    assert stolen.token != acquired.token


def test_redis_down_falls_back_to_local_single_flight() -> None:
    fake = FakeRedis()
    gateway = _gateway(fake)
    flight = DistributedSingleFlight(gateway, lock_ttl_seconds=30, wait_seconds=0.5)
    guard = ScrapeGuard(
        result_cache_ttl_seconds=60,
        cache=ResponseCache(),
        distributed_flight=flight,
        distributed_lock_enabled=True,
        url_cooldown_seconds=0,
        domain_min_interval_seconds=0,
    )
    fake.fail_next = True
    url = "https://nissei.com/py/redis-down"
    calls = {"n": 0}

    def _fn() -> str:
        calls["n"] += 1
        return "ok"

    assert guard.run_coalesced(url, _fn) == "ok"
    assert calls["n"] == 1
