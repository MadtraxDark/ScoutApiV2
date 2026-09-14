"""In-memory Redis stand-in for unit tests (subset of redis-py sync API)."""

from __future__ import annotations

import time
from typing import Any


class FakeRedis:
    """Minimal Redis-compatible store: GET/SET NX PX|EX, PTTL, DEL, EVAL, PING."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, float | None]] = {}
        self.fail_next: bool = False
        self.closed: bool = False

    def _purge(self, key: str) -> None:
        entry = self._data.get(key)
        if entry is None:
            return
        _value, expires_at = entry
        if expires_at is not None and expires_at <= time.monotonic():
            self._data.pop(key, None)

    def _norm_key(self, key: bytes | str) -> str:
        if isinstance(key, bytes):
            return key.decode("utf-8")
        return key

    def ping(self) -> bool:
        self._maybe_fail()
        return True

    def get(self, key: bytes | str) -> bytes | None:
        self._maybe_fail()
        k = self._norm_key(key)
        self._purge(k)
        entry = self._data.get(k)
        return None if entry is None else entry[0]

    def set(
        self,
        key: bytes | str,
        value: bytes | str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        self._maybe_fail()
        k = self._norm_key(key)
        self._purge(k)
        if nx and k in self._data:
            return None
        raw = value if isinstance(value, bytes) else value.encode("utf-8")
        expires_at: float | None = None
        if px is not None:
            expires_at = time.monotonic() + (px / 1000.0)
        elif ex is not None:
            expires_at = time.monotonic() + float(ex)
        self._data[k] = (raw, expires_at)
        return True

    def pttl(self, key: bytes | str) -> int:
        self._maybe_fail()
        k = self._norm_key(key)
        self._purge(k)
        entry = self._data.get(k)
        if entry is None:
            return -2
        _value, expires_at = entry
        if expires_at is None:
            return -1
        remaining_ms = int((expires_at - time.monotonic()) * 1000)
        return remaining_ms if remaining_ms > 0 else -2

    def delete(self, *keys: bytes | str) -> int:
        self._maybe_fail()
        removed = 0
        for key in keys:
            k = self._norm_key(key)
            if self._data.pop(k, None) is not None:
                removed += 1
        return removed

    def eval(self, script: str, numkeys: int, *keys_and_args: Any) -> int:
        self._maybe_fail()
        del script
        keys = keys_and_args[:numkeys]
        args = keys_and_args[numkeys:]
        key = self._norm_key(keys[0])
        expected = args[0]
        if isinstance(expected, str):
            expected = expected.encode("utf-8")
        self._purge(key)
        entry = self._data.get(key)
        if entry is not None and entry[0] == expected:
            self._data.pop(key, None)
            return 1
        return 0

    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)

    def close(self) -> None:
        self.closed = True

    def _maybe_fail(self) -> None:
        if self.fail_next:
            self.fail_next = False
            from redis.exceptions import RedisError

            raise RedisError("simulated redis failure")


class FakeRedisPipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def get(self, key: bytes | str) -> FakeRedisPipeline:
        self._ops.append(("get", (key,)))
        return self

    def pttl(self, key: bytes | str) -> FakeRedisPipeline:
        self._ops.append(("pttl", (key,)))
        return self

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args in self._ops:
            results.append(getattr(self._redis, name)(*args))
        return results
