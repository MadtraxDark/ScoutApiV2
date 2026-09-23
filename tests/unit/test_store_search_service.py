"""StoreSearchService — empty SERP classification (incomplete ≠ NO_MATCH)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from scrapy.http import HtmlResponse

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.matching.search_adapters.brazil.amazon import (
    AmazonBrazilSearchAdapter,
)
from scout_api.modules.matching.search_adapters.paraguay.visaovip import (
    VisaoVipSearchAdapter,
)
from scout_api.modules.matching.store_search_service import StoreSearchService


def _html(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(url=url, body=body.encode("utf-8"), encoding="utf-8")


def test_visaovip_incomplete_shell_is_search_incomplete_response() -> None:
    """Incomplete SERP shell emits SEARCH_INCOMPLETE_RESPONSE (Task 10 taxonomy)."""
    fetcher = MagicMock()
    fetcher.fetch.return_value = _html(
        "https://www.visaovip.com/busca/termo/ASUS-TUF/",
        "<html><body><div>loading</div></body></html>",
    )
    service = StoreSearchService(fetcher=fetcher)
    with pytest.raises(RequestError) as exc:
        service.search("visaovip", "ASUS TUF")
    # New preferred taxonomy code (UPSTREAM_BLOCKED was legacy alias).
    assert exc.value.code == "SEARCH_INCOMPLETE_RESPONSE"


def test_amazon_incomplete_shell_is_search_incomplete_response() -> None:
    """Incomplete SERP shell emits SEARCH_INCOMPLETE_RESPONSE (Task 10 taxonomy)."""
    fetcher = MagicMock()
    fetcher.fetch.return_value = _html(
        "https://www.amazon.com.br/s?k=test",
        "<html><body><div id='search'>shell</div></body></html>",
    )
    service = StoreSearchService(fetcher=fetcher)
    with pytest.raises(RequestError) as exc:
        service.search("amazon_br", "test")
    # New preferred taxonomy code (UPSTREAM_BLOCKED was legacy alias).
    assert exc.value.code == "SEARCH_INCOMPLETE_RESPONSE"


def test_visaovip_classify_genuine_empty() -> None:
    adapter = VisaoVipSearchAdapter()
    response = _html(
        "https://www.visaovip.com/busca/termo/xyz/",
        "<html><body>Nenhum resultado encontrado</body></html>",
    )
    assert adapter.classify_empty_result(response) == "genuine_empty"


def test_amazon_classify_genuine_empty() -> None:
    adapter = AmazonBrazilSearchAdapter()
    response = _html(
        "https://www.amazon.com.br/s?k=xyz",
        "<html><body>Nenhum resultado para xyz</body></html>",
    )
    assert adapter.classify_empty_result(response) == "genuine_empty"


def test_prefer_browser_on_visaovip_request_not_on_amazon() -> None:
    assert VisaoVipSearchAdapter().build_search_request("board").prefer_browser is True
    assert (
        AmazonBrazilSearchAdapter().build_search_request("phone").prefer_browser
        is False
    )
