import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float


class ResponseCache:
    def __init__(self) -> None:
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry and entry.expires_at > time.monotonic():
            return entry.value
        self._entries.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._entries[key] = CacheEntry(value, time.monotonic() + ttl)
