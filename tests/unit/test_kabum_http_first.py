"""Tests for KaBuM HTTP-first progressive fetcher."""

from __future__ import annotations

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.services.kabum_http_first_fetcher import (
    KabumHttpFirstHtmlFetcher,
    looks_like_kabum_pdp,
    looks_like_kabum_search,
)


def _html_response(url: str, body: str) -> HtmlResponse:
    raw = body.encode("utf-8")
    return HtmlResponse(url, body=raw, encoding="utf-8", request=Request(url))


class _RecordingFetcher:
    def __init__(
        self, response: HtmlResponse | None = None, error: Exception | None = None
    ):
        self.response = response
        self.error = error
        self.calls: list[str] = []

    def fetch(self, url: str) -> HtmlResponse:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_kabum_search_http_accepted() -> None:
    url = "https://www.kabum.com.br/busca/rtx%205060"
    body = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"data":{"catalogServer":{"data":[{"code":1}]}}}}}'
        "</script>"
    )
    http = _RecordingFetcher(_html_response(url, body))
    browser = _RecordingFetcher(_html_response(url, "browser"))
    assert looks_like_kabum_search(_html_response(url, body))
    response = KabumHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert browser.calls == []
    assert response.meta["fetch_metrics"]["fetch_strategy"] == "http-direct"


def test_kabum_challenge_falls_back_to_browser() -> None:
    url = "https://www.kabum.com.br/produto/1"
    challenge = _html_response(url, "<html></html>")
    # Force challenge via title helper path: empty body without NEXT_DATA → browser
    http = _RecordingFetcher(challenge)
    browser = _RecordingFetcher(_html_response(url, "<html>browser</html>"))
    response = KabumHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert browser.calls == [url]
    assert response.text == "<html>browser</html>"


def test_kabum_http_error_falls_back() -> None:
    url = "https://www.kabum.com.br/busca/x"
    http = _RecordingFetcher(
        error=RequestError("blocked", code="UPSTREAM_BLOCKED", url=url)
    )
    browser = _RecordingFetcher(_html_response(url, "browser"))
    response = KabumHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert browser.calls == [url]
    assert response.text == "browser"


def test_non_kabum_skips_http() -> None:
    url = "https://www.amazon.com.br/dp/B09WNK39JN"
    http = _RecordingFetcher(_html_response(url, "http"))
    browser = _RecordingFetcher(_html_response(url, "browser"))
    KabumHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert http.calls == []
    assert browser.calls == [url]


def test_kabum_pdp_next_data_accepted() -> None:
    url = "https://www.kabum.com.br/produto/123/placa"
    body = '<script id="__NEXT_DATA__">{"props":{}}</script><h1>Placa</h1>'
    assert looks_like_kabum_pdp(_html_response(url, body))
    http = _RecordingFetcher(_html_response(url, body))
    browser = _RecordingFetcher(_html_response(url, "browser"))
    KabumHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert browser.calls == []
