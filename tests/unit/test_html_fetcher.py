from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.services.html_fetcher import (
    CamoufoxHtmlFetcher,
    UrllibHtmlFetcher,
    is_challenge_page,
)
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)


def test_is_challenge_page_detects_cloudflare_and_akamai() -> None:
    assert is_challenge_page("<html></html>", title="Just a moment...")
    assert is_challenge_page(
        '<link rel="stylesheet" href="https://wx.mlcdn.com.br/akamai-bot/css/x.css">'
        "<h1>Não é possível acessar a página</h1>"
    )
    assert not is_challenge_page(
        "<html><body><h1>Produto</h1><p>R$ 10,00</p></body></html>",
        title="Produto",
    )


def test_urllib_fetcher_maps_http_403() -> None:
    def opener(request: Any, timeout: int = 30) -> Any:
        del timeout
        raise HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    fetcher = UrllibHtmlFetcher(opener=opener, user_agent="test", timeout=5)
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://www.magazineluiza.com.br/p/1")
    assert exc.value.code == "UPSTREAM_BLOCKED"


def test_camoufox_fetcher_returns_html_response() -> None:
    html = (
        "<html><head><title>PS5</title></head><body>"
        "<h1>PlayStation 5</h1>"
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"PlayStation 5","sku":"240590700",'
        '"offers":{"price":"4399.00","availability":"InStock"}}'
        "</script></body></html>"
    )

    class FakePage:
        url = "https://www.magazineluiza.com.br/p/240590700"

        def goto(self, url: str, **kwargs: Any) -> None:
            del url, kwargs

        def content(self) -> str:
            return html

        def title(self) -> str:
            return "PS5"

        def wait_for_timeout(self, ms: int) -> None:
            del ms

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=1,
    )
    response = fetcher.fetch("https://www.magazineluiza.com.br/p/240590700")
    assert isinstance(response, HtmlResponse)
    assert "PlayStation 5" in response.text


def test_camoufox_fetcher_raises_when_challenge_persists() -> None:
    class FakePage:
        url = "https://nissei.com/py/x"

        def goto(self, url: str, **kwargs: Any) -> None:
            del url, kwargs

        def content(self) -> str:
            return "<html><body>Performing security verification</body></html>"

        def title(self) -> str:
            return "Just a moment..."

        def wait_for_timeout(self, ms: int) -> None:
            del ms

    class FakeBrowser:
        def new_page(self) -> FakePage:
            return FakePage()

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[FakeBrowser]:
        del kwargs
        yield FakeBrowser()

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        settle_ms=0,
        max_settle_attempts=2,
    )
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://nissei.com/py/x")
    assert exc.value.code == "UPSTREAM_BLOCKED"


def test_product_scrape_service_uses_fetcher_and_spider() -> None:
    html = (
        b"<html><body><h1>PlayStation 5</h1>"
        b'<script type="application/ld+json">'
        b'{"@type":"Product","name":"PlayStation 5","sku":"240590700",'
        b'"offers":{"price":"4399.00","availability":"https://schema.org/InStock"}}'
        b"</script>"
        b"<button>Adicionar \xc3\xa0 sacola</button></body></html>"
    )
    url = "https://www.magazineluiza.com.br/p/240590700"

    class FakeFetcher:
        def fetch(self, fetch_url: str) -> HtmlResponse:
            return HtmlResponse(
                fetch_url,
                body=html,
                encoding="utf-8",
                request=Request(fetch_url),
            )

    item = ProductScrapeService(fetcher=FakeFetcher()).scrape(url)
    assert item.product_id == "240590700"
    assert item.price == Decimal("4399.00")
    assert item.store == "magazineluiza"


def test_product_scrape_service_supports_nissei_domain() -> None:
    html = (
        b"<html><body><h1>Placa Madre</h1>"
        b'<meta itemprop="price" content="3227000">'
        b"<span>SKU 148321</span><span>En stock</span></body></html>"
    )
    url = (
        "https://nissei.com/py/informatica/placa-madre-gigabyte-am5-x870-aorus-"
        "stealth-ice-hdmi-usb3-2-4m-2-ddr5-atx"
    )

    class FakeFetcher:
        def fetch(self, fetch_url: str) -> HtmlResponse:
            return HtmlResponse(
                fetch_url,
                body=html,
                encoding="utf-8",
                request=Request(fetch_url),
            )

    item = ProductScrapeService(fetcher=FakeFetcher()).scrape(url)
    assert item.store == "nissei"
    assert item.sku == "148321"
    assert item.price == Decimal("3227000")
