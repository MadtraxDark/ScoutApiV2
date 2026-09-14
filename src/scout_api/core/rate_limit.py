"""Fixed-window rate limiting with Redis (preferred) or in-process fallback."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from scout_api.core.config import Settings, get_settings
from scout_api.modules.crawler.core.redis_client import (
    RedisGateway,
    build_redis_gateway,
)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int
    scope: str


class _MemoryWindow:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, float]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = time.monotonic()
        with self._lock:
            count, reset_at = self._buckets.get(key, (0, now + window_seconds))
            if now >= reset_at:
                count, reset_at = 0, now + window_seconds
            count += 1
            self._buckets[key] = (count, reset_at)
            retry = max(1, int(reset_at - now))
            if count > limit:
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    retry_after=retry,
                    scope=key.split(":", 1)[0],
                )
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - count),
                retry_after=retry,
                scope=key.split(":", 1)[0],
            )


class RateLimiter:
    """API client rate limiter (not marketplace crawl throttling)."""

    def __init__(
        self,
        settings: Settings | None = None,
        redis_gateway: RedisGateway | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._redis = redis_gateway
        if self._redis is None and self._settings.redis_url:
            self._redis = build_redis_gateway(self._settings)
        self._memory = _MemoryWindow()

    def check(
        self,
        *,
        scope: str,
        identity: str,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitResult:
        if not self._settings.rate_limit_enabled:
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit,
                retry_after=0,
                scope=scope,
            )
        key = f"rl:{scope}:{identity}"
        if self._redis is not None:
            client = self._redis.get_client()
            if client is not None:
                try:
                    pipe = client.pipeline()
                    pipe.incr(key)
                    pipe.expire(key, window_seconds)
                    count, _ = pipe.execute()
                    count_i = int(count)
                    ttl = int(client.ttl(key) or window_seconds)
                    if count_i > limit:
                        return RateLimitResult(
                            allowed=False,
                            limit=limit,
                            remaining=0,
                            retry_after=max(1, ttl),
                            scope=scope,
                        )
                    return RateLimitResult(
                        allowed=True,
                        limit=limit,
                        remaining=max(0, limit - count_i),
                        retry_after=max(1, ttl),
                        scope=scope,
                    )
                except Exception:
                    pass
        result = self._memory.hit(key, limit, window_seconds)
        return RateLimitResult(
            allowed=result.allowed,
            limit=result.limit,
            remaining=result.remaining,
            retry_after=result.retry_after,
            scope=scope,
        )


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def reset_rate_limiter() -> None:
    global _limiter
    _limiter = None
