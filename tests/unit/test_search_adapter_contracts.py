"""Contract smoke for every registered StoreSearchAdapter."""

from __future__ import annotations

import pytest
from scrapy.http import HtmlResponse

from scout_api.modules.matching.search_adapters.registry import (
    registered_search_store_keys,
    reset_search_adapter_registry,
    resolve_search_adapter,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    reset_search_adapter_registry()


@pytest.mark.parametrize("store_key", registered_search_store_keys())
def test_search_adapter_builds_http_get_request(store_key: str) -> None:
    adapter = resolve_search_adapter(store_key)
    assert adapter.store_key == store_key
    request = adapter.build_search_request("Samsung Galaxy S25 Ultra")
    assert request.method == "GET"
    assert request.url.startswith("http")
    assert " " not in request.url.split("?", 1)[0] or "%20" in request.url


@pytest.mark.parametrize("store_key", registered_search_store_keys())
def test_search_adapter_empty_query_or_minimal(store_key: str) -> None:
    adapter = resolve_search_adapter(store_key)
    # Empty query: either raises or builds a URL — must not return empty url.
    try:
        request = adapter.build_search_request("   ")
    except Exception:
        return
    assert request.url


@pytest.mark.parametrize("store_key", registered_search_store_keys())
def test_search_adapter_classify_empty_on_blank_html(store_key: str) -> None:
    adapter = resolve_search_adapter(store_key)
    response = HtmlResponse(
        url="https://example.com/search",
        body=b"<html><body></body></html>",
        encoding="utf-8",
    )
    result = adapter.classify_empty_result(response)
    assert result in {"genuine_empty", "incomplete", "unknown"}
