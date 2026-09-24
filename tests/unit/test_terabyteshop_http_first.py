"""TerabyteShop HTTP-first progressive fetch tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.services.terabyteshop_http_first_fetcher import (
    TerabyteShopHttpFirstHtmlFetcher,
    is_terabyteshop_store_url,
    looks_like_terabyteshop_pdp,
    looks_like_terabyteshop_search,
)


def _response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(
        url, body=body.encode("utf-8"), encoding="utf-8", request=Request(url)
    )


def test_is_terabyteshop_store_url() -> None:
    assert is_terabyteshop_store_url("https://www.terabyteshop.com.br/produto/1/x")
    assert not is_terabyteshop_store_url("https://www.pichau.com.br/x")


def test_looks_like_terabyteshop_pdp_with_json_ld() -> None:
    html = (
        "<html><head><script type='application/ld+json'>"
        '{"@type":"Product","name":"X","offers":{"price":"10"}}'
        "</script></head><body><h1>X</h1><p id='valVista'>R$ 10,00</p>"
        "</body></html>"
    )
    assert looks_like_terabyteshop_pdp(
        _response("https://www.terabyteshop.com.br/produto/1/x", html)
    )


def test_looks_like_terabyteshop_pdp_rejects_challenge() -> None:
    html = "<html><title>Just a moment...</title><body>cloudflare</body></html>"
    assert not looks_like_terabyteshop_pdp(
        _response("https://www.terabyteshop.com.br/produto/1/x", html)
    )


def test_looks_like_terabyteshop_search() -> None:
    html = (
        "<html><body>"
        "<a href='/produto/10/a'>A</a>"
        "<a href='/produto/11/b'>B</a>"
        "</body></html>"
    )
    assert looks_like_terabyteshop_search(
        _response("https://www.terabyteshop.com.br/busca?str=placa", html)
    )


def test_terabyte_http_first_accepts_pdp() -> None:
    html = (
        "<html><head><script type='application/ld+json'>"
        '{"@type":"Product","offers":{"price":"10"}}'
        "</script></head><body>"
        "<h1>Prod</h1><p id='valVista'>R$ 10,00</p>"
        "</body></html>"
    )
    http = MagicMock()
    http.fetch.return_value = _response(
        "https://www.terabyteshop.com.br/produto/1/x", html
    )
    browser = MagicMock()
    fetcher = TerabyteShopHttpFirstHtmlFetcher(http=http, browser=browser)
    result = fetcher.fetch("https://www.terabyteshop.com.br/produto/1/x")
    http.fetch.assert_called_once()
    browser.fetch.assert_not_called()
    assert result.meta["fetch_metrics"]["fetch_strategy"] == "http-direct"
    assert result.meta["fetch_metrics"]["browser_used"] is False


def test_terabyte_http_first_falls_back_on_challenge() -> None:
    challenge = (
        "<html><title>Just a moment...</title>"
        "<body>cloudflare challenge-platform</body></html>"
    )
    browser_html = (
        "<html><head><script type='application/ld+json'>"
        '{"@type":"Product","offers":{"price":"10"}}'
        "</script></head><body><h1>Ok</h1></body></html>"
    )
    url = "https://www.terabyteshop.com.br/produto/1/x"
    http = MagicMock()
    http.fetch.return_value = _response(url, challenge)
    browser = MagicMock()
    browser.fetch.return_value = _response(url, browser_html)
    fetcher = TerabyteShopHttpFirstHtmlFetcher(http=http, browser=browser)
    result = fetcher.fetch(url)
    browser.fetch.assert_called_once()
    assert "Product" in (result.text or "")


def test_terabyte_http_first_falls_back_on_network_error() -> None:
    url = "https://www.terabyteshop.com.br/produto/1/x"
    http = MagicMock()
    http.fetch.side_effect = RequestError(
        "fail", code="UPSTREAM_NETWORK_ERROR", url=url
    )
    browser = MagicMock()
    browser.fetch.return_value = _response(
        url,
        "<html><head><script type='application/ld+json'>"
        '{"@type":"Product","offers":{"price":"10"}}'
        "</script></head><body><h1>Ok</h1></body></html>",
    )
    fetcher = TerabyteShopHttpFirstHtmlFetcher(http=http, browser=browser)
    fetcher.fetch(url)
    browser.fetch.assert_called_once()


def test_non_terabyte_delegates_to_browser() -> None:
    http = MagicMock()
    browser = MagicMock()
    browser.fetch.return_value = _response("https://www.pichau.com.br/x", "ok")
    fetcher = TerabyteShopHttpFirstHtmlFetcher(http=http, browser=browser)
    fetcher.fetch("https://www.pichau.com.br/x")
    http.fetch.assert_not_called()
    browser.fetch.assert_called_once()
