from ..spiders.registry import (
    resolve_spider_by_store_key,
    resolve_store_spider,
    stores_supporting_search,
)
from ..stores import STORE_CONFIGS, match_enabled_store_keys


def eligible_match_store_keys() -> tuple[str, ...]:
    """Stores that may run in Product Match auto-discovery.

    Intersection of:
    - registered catalog entries (``STORE_CONFIGS``)
    - ``implemented=True``
    - ``match_enabled=True`` (temporary exclusions live here)
    - spider ``supports_search=True``

    Implemented stores without search (or with ``match_enabled=False``) are
    omitted — they are not ERROR / NO_MATCH for that match operation.
    """
    search_ok = set(stores_supporting_search())
    return tuple(key for key in match_enabled_store_keys() if key in search_ok)


def store_match_disabled_reason(store_key: str) -> str | None:
    config = STORE_CONFIGS.get(store_key)
    if config is None:
        return None
    if config.match_enabled:
        return None
    return config.match_disabled_reason


__all__ = [
    "resolve_store_spider",
    "resolve_spider_by_store_key",
    "stores_supporting_search",
    "eligible_match_store_keys",
    "store_match_disabled_reason",
]
