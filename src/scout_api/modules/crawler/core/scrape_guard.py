"""Politeness guard: block repeated upstream fetches that burn egress IP reputation."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock
from typing import TypeVar
from urllib.parse import urlparse

from ..models.product import (
    ProductOffer,
    ProductPriceItem,
    product_offer_from_price_item,
)
from .cache import ResponseCache
from .exceptions import RequestError
from .fingerprints import canonicalize_url
from .single_flight import SingleFlight

T = TypeVar("T")


class ScrapeGuard:
    """In-process URL cooldown, domain spacing, result cache, and single-flight.

    Protects Camoufox/egress IPs from bursty ``POST /crawl`` retries against the
    same product or store host (Cloudflare hard-blocks). Caches both full
    ``ProductPriceItem`` and lightweight ``ProductOffer`` under the same
    canonical key (full item wins when both exist).
    """

    def __init__(
        self,
        *,
        url_cooldown_seconds: int = 300,
        domain_min_interval_seconds: float = 15.0,
        result_cache_ttl_seconds: int = 300,
        cache: ResponseCache | None = None,
        single_flight: SingleFlight | None = None,
    ) -> None:
        self._url_cooldown_seconds = max(0, url_cooldown_seconds)
        self._domain_min_interval_seconds = max(0.0, domain_min_interval_seconds)
        self._result_cache_ttl_seconds = max(0, result_cache_ttl_seconds)
        self._cache = cache or ResponseCache()
        self._single_flight = single_flight or SingleFlight()
        self._url_blocked_until: dict[str, float] = {}
        self._domain_next_ok: dict[str, float] = {}
        self._lock = Lock()

    def get_cached(self, url: str) -> ProductPriceItem | None:
        cached = self._cache.get(self._cache_key(url))
        if cached is None:
            return None
        if not isinstance(cached, ProductPriceItem):
            return None
        return cached.model_copy(
            update={
                "metadata": {
                    **cached.metadata,
                    "cache_hit": True,
                    "served_from": "scrape_guard",
                }
            }
        )

    def get_cached_offer(self, url: str) -> ProductOffer | None:
        """Return a cached offer, projecting from a full item when available."""
        cached = self._cache.get(self._cache_key(url))
        if cached is None:
            return None
        if isinstance(cached, ProductOffer):
            return cached.model_copy(
                update={
                    "metadata": {
                        **cached.metadata,
                        "cache_hit": True,
                        "served_from": "scrape_guard",
                    }
                }
            )
        if isinstance(cached, ProductPriceItem):
            offer = product_offer_from_price_item(cached)
            return offer.model_copy(
                update={
                    "metadata": {
                        **offer.metadata,
                        "cache_hit": True,
                        "served_from": "scrape_guard",
                    }
                }
            )
        return None

    def acquire_for_live_fetch(self, url: str) -> None:
        """Reserve URL/domain for a live fetch or raise ``RequestError``."""
        key = self._cache_key(url)
        host = (urlparse(url).hostname or "").lower()
        now = time.monotonic()
        with self._lock:
            url_until = self._url_blocked_until.get(key, 0.0)
            if url_until > now:
                retry_after = max(1, int(url_until - now))
                raise RequestError(
                    "Requisição repetida para a mesma URL; aguarde o cooldown "
                    f"({retry_after}s) para proteger o IP de saída",
                    code="DUPLICATE_REQUEST",
                    url=url,
                    retryable=True,
                    retry_after=retry_after,
                )

            domain_until = self._domain_next_ok.get(host, 0.0)
            if host and domain_until > now:
                retry_after = max(1, int(domain_until - now))
                raise RequestError(
                    "Muitas requisições seguidas para a mesma loja; aguarde "
                    f"({retry_after}s) para proteger o IP de saída",
                    code="RATE_LIMITED",
                    url=url,
                    retryable=True,
                    retry_after=retry_after,
                )

            self._url_blocked_until[key] = now + self._url_cooldown_seconds
            if host:
                self._domain_next_ok[host] = now + self._domain_min_interval_seconds
            self._purge_expired_locked(now)

    def store_success(self, url: str, item: ProductPriceItem) -> None:
        self._cache.set(self._cache_key(url), item, self._result_cache_ttl_seconds)

    def store_offer_success(self, url: str, offer: ProductOffer) -> None:
        """Cache an offer without downgrading an existing full product entry."""
        key = self._cache_key(url)
        existing = self._cache.get(key)
        if isinstance(existing, ProductPriceItem):
            return
        self._cache.set(key, offer, self._result_cache_ttl_seconds)

    def run_coalesced(self, url: str, fn: Callable[[], T]) -> T:
        """Coalesce concurrent live work for the same canonical URL."""
        return self._single_flight.do(self._cache_key(url), fn)

    @staticmethod
    def _cache_key(url: str) -> str:
        return canonicalize_url(url)

    def _purge_expired_locked(self, now: float) -> None:
        expired_urls = [
            k for k, until in self._url_blocked_until.items() if until <= now
        ]
        for key in expired_urls:
            self._url_blocked_until.pop(key, None)
        expired_hosts = [
            host for host, until in self._domain_next_ok.items() if until <= now
        ]
        for host in expired_hosts:
            self._domain_next_ok.pop(host, None)
