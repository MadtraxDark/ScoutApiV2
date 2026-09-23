from __future__ import annotations

from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.services.pichau_http_first_fetcher import (
    PichauHttpFirstHtmlFetcher,
    is_pichau_store_url,
    looks_like_pichau_pdp,
)


def _response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(
        url, body=body.encode("utf-8"), encoding="utf-8", request=Request(url)
    )


def test_is_pichau_store_url() -> None:
    assert is_pichau_store_url("https://www.pichau.com.br/foo")
    assert not is_pichau_store_url("https://www.kabum.com.br/foo")


def test_looks_like_pichau_pdp_with_prices() -> None:
    html = (
        '<html><body>self.__next_f.push([1,"x"]) '
        '"pichau_prices":{"avista":1}</body></html>'
    )
    assert looks_like_pichau_pdp(_response("https://www.pichau.com.br/x", html))


def test_pichau_http_first_accepts_pdp() -> None:
    html = (
        "<html><head><script type='application/ld+json'>"
        '{"@type":"Product","offers":{"price":"10"}}'
        "</script></head><body>"
        'pichau_prices avista final_price self.__next_f.push([1,"x"])'
        "</body></html>"
    )
    http = MagicMock()
    http.fetch.return_value = _response("https://www.pichau.com.br/sku", html)
    browser = MagicMock()
    fetcher = PichauHttpFirstHtmlFetcher(http=http, browser=browser)
    result = fetcher.fetch("https://www.pichau.com.br/sku")
    http.fetch.assert_called_once()
    browser.fetch.assert_not_called()
    assert result.meta["fetch_metrics"]["fetch_strategy"] == "http-direct"
    assert result.meta["fetch_metrics"]["browser_used"] is False


def test_pichau_http_first_falls_back_on_challenge() -> None:
    challenge = "<html><title>Just a moment...</title><body>cloudflare</body></html>"
    browser_html = (
        "<html><body>pichau_prices avista final_price "
        'self.__next_f.push([1,"x"])</body></html>'
    )
    http = MagicMock()
    http.fetch.return_value = _response("https://www.pichau.com.br/sku", challenge)
    browser = MagicMock()
    browser.fetch.return_value = _response(
        "https://www.pichau.com.br/sku", browser_html
    )
    fetcher = PichauHttpFirstHtmlFetcher(http=http, browser=browser)
    result = fetcher.fetch("https://www.pichau.com.br/sku")
    browser.fetch.assert_called_once()
    assert "pichau_prices" in (result.text or "")


def test_pichau_http_first_falls_back_on_network_error() -> None:
    http = MagicMock()
    http.fetch.side_effect = RequestError(
        "fail", code="UPSTREAM_NETWORK_ERROR", url="https://www.pichau.com.br/sku"
    )
    browser = MagicMock()
    browser.fetch.return_value = _response(
        "https://www.pichau.com.br/sku",
        "pichau_prices avista final_price",
    )
    fetcher = PichauHttpFirstHtmlFetcher(http=http, browser=browser)
    fetcher.fetch("https://www.pichau.com.br/sku")
    browser.fetch.assert_called_once()


def test_non_pichau_delegates_to_browser() -> None:
    http = MagicMock()
    browser = MagicMock()
    browser.fetch.return_value = _response("https://www.kabum.com.br/x", "ok")
    fetcher = PichauHttpFirstHtmlFetcher(http=http, browser=browser)
    fetcher.fetch("https://www.kabum.com.br/x")
    http.fetch.assert_not_called()
    browser.fetch.assert_called_once()
