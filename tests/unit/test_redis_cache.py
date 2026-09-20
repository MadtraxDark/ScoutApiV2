"""Unit tests for scrape ResponseCache backends and serialization."""

from __future__ import annotations

from decimal import Decimal

import pytest
from tests.unit.fakes.fake_redis import FakeRedis

from scout_api.modules.crawler.core.cache import (
    KIND_OFFER,
    KIND_PRODUCT,
    SCHEMA_VERSION,
    HybridCacheBackend,
    InMemoryCacheBackend,
    RedisCacheBackend,
    ResponseCache,
    build_cache_backend,
    deserialize_cache_value,
    serialize_cache_value,
)
from scout_api.modules.crawler.core.redis_client import RedisGateway, redact_redis_url
from scout_api.modules.crawler.core.redis_keys import scrape_cache_key, url_digest
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.models.product import ProductOffer, ProductPriceItem


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


def _offer(url: str) -> ProductOffer:
    return ProductOffer(
        store="nissei",
        country="PY",
        product_id="1",
        url=url,
        canonical_url=url,
        currency="PYG",
        price=Decimal("1000"),
    )


def _gateway(fake: FakeRedis | None = None) -> RedisGateway:
    client = fake if fake is not None else FakeRedis()
    return RedisGateway("redis://localhost:6379/0", client=client)


def test_serialize_roundtrip_product_and_offer() -> None:
    url = "https://nissei.com/py/a"
    item = _item(url)
    offer = _offer(url)
    raw_item = serialize_cache_value(item)
    raw_offer = serialize_cache_value(offer)
    assert deserialize_cache_value(raw_item) == item
    assert deserialize_cache_value(raw_offer) == offer
    assert KIND_PRODUCT in raw_item.decode()
    assert KIND_OFFER in raw_offer.decode()
    assert f'"schema_version":{SCHEMA_VERSION}' in raw_item.decode()


def test_invalid_payload_and_schema_are_miss() -> None:
    assert deserialize_cache_value(b"not-json") is None
    assert (
        deserialize_cache_value(
            b'{"schema_version":999,"kind":"product_price_item","payload":{}}'
        )
        is None
    )
    cache = ResponseCache(backend=InMemoryCacheBackend())
    cache.backend.set("k", b"garbage", 60)
    assert cache.get("k") is None
    assert cache.get("k") is None  # key deleted


def test_memory_backend_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = InMemoryCacheBackend()
    backend.set("k", b"v", ttl=10)
    assert backend.get("k") == b"v"
    monkeypatch.setattr(
        "scout_api.modules.crawler.core.cache.time.monotonic",
        lambda: 1_000_000.0,
    )
    # Force expiry by rewriting with past clock after set at real time — use short ttl.
    backend2 = InMemoryCacheBackend()
    now = 100.0
    monkeypatch.setattr(
        "scout_api.modules.crawler.core.cache.time.monotonic", lambda: now
    )
    backend2.set("k", b"v", ttl=1)
    now = 102.0
    assert backend2.get("k") is None


def test_redis_backend_set_get_and_connection_error() -> None:
    fake = FakeRedis()
    backend = RedisCacheBackend(_gateway(fake))
    backend.set("k", b"hello", 30)
    assert backend.get("k") == b"hello"

    fake.fail_next = True
    assert backend.get("k") is None  # fail-open miss


def test_hybrid_populates_l1_from_redis() -> None:
    fake = FakeRedis()
    gateway = _gateway(fake)
    l1 = InMemoryCacheBackend()
    l2 = RedisCacheBackend(gateway)
    hybrid = HybridCacheBackend(l1, l2)
    cache = ResponseCache(backend=hybrid)
    url = "https://nissei.com/py/hybrid"
    key = scrape_cache_key(url)
    cache.set(key, _item(url), 60)

    # Fresh L1 miss path: clear L1 only.
    l1.delete(key)
    hit = cache.lookup(key)
    assert hit is not None
    assert hit.served_from == "redis"
    assert isinstance(hit.value, ProductPriceItem)

    hit2 = cache.lookup(key)
    assert hit2 is not None
    assert hit2.served_from == "memory"


def test_build_cache_backend_without_redis_is_memory() -> None:
    backend = build_cache_backend(redis_gateway=None)
    assert isinstance(backend, InMemoryCacheBackend)


def test_build_cache_backend_with_gateway_is_hybrid() -> None:
    backend = build_cache_backend(redis_gateway=_gateway())
    assert isinstance(backend, HybridCacheBackend)


def test_product_not_overwritten_by_offer() -> None:
    fake = FakeRedis()
    cache = ResponseCache(backend=build_cache_backend(redis_gateway=_gateway(fake)))
    guard = ScrapeGuard(
        url_cooldown_seconds=60,
        domain_min_interval_seconds=0,
        result_cache_ttl_seconds=60,
        cache=cache,
    )
    url = "https://nissei.com/py/precedence"
    guard.store_success(url, _item(url))
    guard.store_offer_success(url, _offer(url))
    assert guard.get_cached(url) is not None
    assert isinstance(cache.get(scrape_cache_key(url)), ProductPriceItem)


def test_canonical_urls_share_key_and_different_urls_differ() -> None:
    a = scrape_cache_key("https://nissei.com/py/x?utm_source=ads")
    b = scrape_cache_key("https://nissei.com/py/x")
    c = scrape_cache_key("https://nissei.com/py/y")
    assert a == b
    assert a != c
    assert url_digest("https://nissei.com/py/x") == url_digest(
        "https://NISSEI.com/py/x/"
    )


def test_redact_redis_url_hides_password() -> None:
    redacted = redact_redis_url("redis://user:secret@redis:6379/0")
    assert "secret" not in redacted
    assert "***" in redacted


def test_fallback_when_redis_down_still_caches_locally() -> None:
    fake = FakeRedis()
    gateway = _gateway(fake)
    cache = ResponseCache(backend=build_cache_backend(redis_gateway=gateway))
    guard = ScrapeGuard(
        result_cache_ttl_seconds=60,
        cache=cache,
        distributed_lock_enabled=False,
        distributed_cooldown_enabled=False,
    )
    url = "https://nissei.com/py/fallback"
    guard.store_success(url, _item(url))
    fake.fail_next = True
    # L1 still serves even if L2 would fail on a fresh write path.
    assert guard.get_cached(url) is not None
