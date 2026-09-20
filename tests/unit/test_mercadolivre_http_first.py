"""Tests for Mercado Livre curl_cffi HTTP-first progressive fetcher."""

from __future__ import annotations

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.services.html_fetcher import (
    is_mercadolivre_snoopy_challenge,
)
from scout_api.modules.crawler.services.mercadolivre_http_first_fetcher import (
    MercadoLivreHttpFirstHtmlFetcher,
    has_mercadolivre_price_signal,
    is_mercadolivre_store_url,
    looks_like_mercadolivre_pdp,
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


def test_is_mercadolivre_store_url() -> None:
    assert is_mercadolivre_store_url("https://www.mercadolivre.com.br/foo/p/MLB1")
    assert is_mercadolivre_store_url(
        "https://produto.mercadolivre.com.br/MLB-12345678-foo"
    )
    assert not is_mercadolivre_store_url("https://www.kabum.com.br/produto/1")


def test_snoopy_challenge_detection() -> None:
    snoopy = (
        "<html><button id='continue-button'></button>"
        "<script>verifyChallenge()</script>"
        "<script src='snoopy-generation-web/x.js'></script></html>"
    )
    assert is_mercadolivre_snoopy_challenge(snoopy)
    assert not is_mercadolivre_snoopy_challenge(
        "<html><h1 class='ui-pdp-title'>GPU</h1>"
        "<meta itemprop='price' content='10'></html>"
    )


def test_http_first_uses_curl_when_price_present() -> None:
    url = "https://www.mercadolivre.com.br/gpu/p/MLB47363706"
    http_body = (
        '<h1 class="ui-pdp-title">GPU</h1>'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"GPU","sku":"MLB47363706",'
        '"offers":{"@type":"Offer","price":100.5,'
        '"priceCurrency":"BRL","availability":'
        '"https://schema.org/InStock"}}'
        "</script>"
    )
    http = _RecordingFetcher(_html_response(url, http_body))
    browser = _RecordingFetcher(_html_response(url, "<html>browser</html>"))
    response = MercadoLivreHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert http.calls == [url]
    assert browser.calls == []
    assert looks_like_mercadolivre_pdp(response)
    assert has_mercadolivre_price_signal(response)
    assert response.meta["fetch_metrics"]["fetch_strategy"] == "curl-cffi-direct"


def test_http_first_falls_back_on_snoopy() -> None:
    url = "https://www.mercadolivre.com.br/gpu/p/MLB47363706"
    snoopy = (
        "<html><title>GPU</title>"
        "<button id='continue-button' disabled>Continuar</button>"
        "<script>function verifyChallenge(){}</script>"
        "<script src='https://http2.mlstatic.com/frontend-assets/"
        "snoopy-generation-web/latest/snoopy-script.js'></script>"
        "</html>"
    )
    browser_body = (
        '<h1 class="ui-pdp-title">GPU</h1>'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"GPU","offers":{"price":10}}'
        "</script>"
    )
    http = _RecordingFetcher(_html_response(url, snoopy))
    browser = _RecordingFetcher(_html_response(url, browser_body))
    response = MercadoLivreHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert http.calls == [url]
    assert browser.calls == [url]
    assert "ui-pdp-title" in response.text


def test_http_first_falls_back_on_blocked_error() -> None:
    url = "https://www.mercadolivre.com.br/gpu/p/MLB47363706"
    http = _RecordingFetcher(
        error=RequestError("blocked", code="UPSTREAM_BLOCKED", url=url, retryable=True)
    )
    browser = _RecordingFetcher(
        _html_response(url, '<h1 class="ui-pdp-title">GPU</h1>')
    )
    response = MercadoLivreHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert browser.calls == [url]
    assert "GPU" in response.text


def test_http_first_accepts_lista_serp_without_pdp_price() -> None:
    from scout_api.modules.crawler.services.mercadolivre_http_first_fetcher import (
        looks_like_mercadolivre_search,
    )

    url = "https://lista.mercadolivre.com.br/gigabyte-rtx-5060"
    http_body = (
        "<html><body class='ui-search-layout'>"
        "<a class='ui-search-link' "
        "href='https://www.mercadolivre.com.br/gpu/p/MLB111'>card</a>"
        "</body></html>"
    )
    http = _RecordingFetcher(_html_response(url, http_body))
    browser = _RecordingFetcher(_html_response(url, "<html>browser</html>"))
    response = MercadoLivreHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert http.calls == [url]
    assert browser.calls == []
    assert looks_like_mercadolivre_search(response)
    assert response.meta["fetch_metrics"]["fetch_strategy"] == "curl-cffi-direct"


def test_http_first_falls_back_on_account_verification() -> None:
    url = "https://lista.mercadolivre.com.br/gigabyte-rtx-5060"
    verify_url = (
        "https://www.mercadolivre.com.br/gz/account-verification"
        "?go=https%3A%2F%2Flista.mercadolivre.com.br%2Fgigabyte"
    )
    http = _RecordingFetcher(
        _html_response(verify_url, "<html><body>Verificação de conta</body></html>")
    )
    browser = _RecordingFetcher(
        _html_response(
            url,
            "<html><a class='ui-search-link' "
            "href='https://www.mercadolivre.com.br/gpu/p/MLB222'>ok</a></html>",
        )
    )
    response = MercadoLivreHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert browser.calls == [url]
    assert "ui-search-link" in response.text


def test_non_ml_url_skips_http_leg() -> None:
    url = "https://www.kabum.com.br/produto/1"
    http = _RecordingFetcher(_html_response(url, "<html>http</html>"))
    browser = _RecordingFetcher(_html_response(url, "<html>browser</html>"))
    response = MercadoLivreHttpFirstHtmlFetcher(http=http, browser=browser).fetch(url)
    assert http.calls == []
    assert browser.calls == [url]
    assert "browser" in response.text
