"""Unit tests for Shopping China quick_search HTTP routing."""

from __future__ import annotations

from scout_api.modules.crawler.services.store_aware_fetcher import (
    is_shoppingchina_quick_search,
)


def test_shoppingchina_quick_search_detection() -> None:
    assert is_shoppingchina_quick_search(
        "https://www.shoppingchina.com.py/quick_search?search=iphone"
    )
    assert not is_shoppingchina_quick_search(
        "https://www.shoppingchina.com.py/produto/celular-x-1"
    )
    assert not is_shoppingchina_quick_search(
        "https://nissei.com/py/catalogsearch/result/?q=iphone"
    )
