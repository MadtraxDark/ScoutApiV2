from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.html_fetcher import (
    CamoufoxHtmlFetcher,
    UrllibHtmlFetcher,
    is_challenge_page,
    is_hard_block_page,
    proxy_settings_from_url,
)
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)


def test_is_challenge_page_detects_cloudflare_and_akamai() -> None:
    assert is_challenge_page("<html></html>", title="Just a moment...")
    assert is_challenge_page("<html></html>", title="Un momento…")
    assert is_challenge_page("<html></html>", title="Loading https://nissei.com/py/x")
    assert is_challenge_page(
        '<link rel="stylesheet" href="https://wx.mlcdn.com.br/akamai-bot/css/x.css">'
        "<h1>Não é possível acessar a página</h1>"
    )
    assert not is_challenge_page(
        "<html><body><h1>Produto</h1><p>R$ 10,00</p></body></html>",
        title="Produto",
    )


def test_is_hard_block_page_detects_cloudflare_ip_ban() -> None:
    assert is_hard_block_page(
        "<html><h1>Sorry, you have been blocked</h1></html>",
        title="Attention Required! | Cloudflare",
    )
    assert not is_hard_block_page(
        "<html><body>Performing security verification</body></html>",
        title="Just a moment...",
    )


def test_proxy_settings_from_url_parses_credentials() -> None:
    assert proxy_settings_from_url("http://user:p%40ss@gate.example:8080") == {
        "server": "http://gate.example:8080",
        "username": "user",
        "password": "p@ss",
    }


def test_locale_and_warmup_for_url() -> None:
    from scout_api.modules.crawler.services.html_fetcher import (
        locale_for_url,
        warmup_url_for,
    )

    assert locale_for_url("https://nissei.com/py/x") == "es-PY"
    assert locale_for_url("https://www.magazineluiza.com.br/p/1") == "pt-BR"
    assert locale_for_url("https://example.com/") is None
    assert warmup_url_for("https://nissei.com/py/produto") == "https://nissei.com/py/"
    assert warmup_url_for("https://www.magazineluiza.com.br/p/1") is None


def test_urllib_fetcher_maps_http_403() -> None:
    def opener(request: Any, timeout: int = 30) -> Any:
        del timeout
        raise HTTPError(request.full_url, 403, "Forbidden", hdrs=None, fp=None)

    fetcher = UrllibHtmlFetcher(opener=opener, user_agent="test", timeout=5)
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://www.magazineluiza.com.br/p/1")
    assert exc.value.code == "UPSTREAM_BLOCKED"


def test_camoufox_fetcher_returns_html_response(tmp_path: Any) -> None:
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
        user_data_dir=tmp_path / "profile",
        warmup_origin=False,
    )
    response = fetcher.fetch("https://www.magazineluiza.com.br/p/240590700")
    assert isinstance(response, HtmlResponse)
    assert "PlayStation 5" in response.text


def test_camoufox_fetcher_raises_when_challenge_persists(tmp_path: Any) -> None:
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
        user_data_dir=tmp_path / "profile",
        warmup_origin=False,
    )
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://nissei.com/py/x")
    assert exc.value.code == "UPSTREAM_BLOCKED"
    assert exc.value.retryable is True


def test_camoufox_fetcher_raises_non_retryable_on_hard_block(tmp_path: Any) -> None:
    class FakePage:
        url = "https://nissei.com/py/x"

        def goto(self, url: str, **kwargs: Any) -> None:
            del url, kwargs

        def content(self) -> str:
            return "<html><h1>Sorry, you have been blocked</h1></html>"

        def title(self) -> str:
            return "Attention Required! | Cloudflare"

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
        user_data_dir=tmp_path / "profile",
        warmup_origin=False,
    )
    with pytest.raises(RequestError) as exc:
        fetcher.fetch("https://nissei.com/py/x")
    assert exc.value.code == "UPSTREAM_BLOCKED"
    assert exc.value.retryable is False
    assert "proxy" in exc.value.args[0].lower()


def test_camoufox_launch_kwargs_include_proxy_profile_and_coop(tmp_path: Any) -> None:
    captured: dict[str, Any] = {}

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[Any]:
        captured.update(kwargs)

        class FakePage:
            url = "https://nissei.com/py/x"
            gotos: list[str] = []

            def goto(self, url: str, **goto_kwargs: Any) -> None:
                self.gotos.append(url)
                del goto_kwargs

            def content(self) -> str:
                return "<html><body><h1>ok</h1></body></html>"

            def title(self) -> str:
                return "ok"

            def wait_for_timeout(self, ms: int) -> None:
                del ms

        class FakeBrowser:
            def new_page(self) -> FakePage:
                return FakePage()

        yield FakeBrowser()

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        proxy_url="http://u:p@proxy.example:9000",
        settle_ms=0,
        max_settle_attempts=1,
        user_data_dir=tmp_path / "profile",
        warmup_origin=True,
    )
    fetcher.fetch("https://nissei.com/py/x")
    assert captured["proxy"] == {
        "server": "http://proxy.example:9000",
        "username": "u",
        "password": "p",
    }
    assert "locale" not in captured
    assert captured["geoip"] is True
    assert captured["persistent_context"] is True
    assert captured["disable_coop"] is True
    assert captured["user_data_dir"] == str(tmp_path / "profile")


def test_camoufox_profile_dir_falls_back_when_unwritable(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = tmp_path / "blocked" / "profile"
    real_mkdir = Path.mkdir

    def selective_mkdir(
        self: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if self == blocked:
            raise PermissionError("denied")
        return real_mkdir(self, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", selective_mkdir)

    captured: dict[str, Any] = {}

    @contextmanager
    def fake_factory(**kwargs: Any) -> Iterator[Any]:
        captured.update(kwargs)

        class FakePage:
            url = "https://www.magazineluiza.com.br/p/1"

            def goto(self, url: str, **goto_kwargs: Any) -> None:
                del url, goto_kwargs

            def content(self) -> str:
                return "<html><body><h1>ok</h1></body></html>"

            def title(self) -> str:
                return "ok"

            def wait_for_timeout(self, ms: int) -> None:
                del ms

        class FakeBrowser:
            def new_page(self) -> FakePage:
                return FakePage()

        yield FakeBrowser()

    fetcher = CamoufoxHtmlFetcher(
        browser_factory=fake_factory,
        user_data_dir=blocked,
        settle_ms=0,
        max_settle_attempts=1,
        warmup_origin=False,
    )
    fetcher.fetch("https://www.magazineluiza.com.br/p/1")

    assert Path(captured["user_data_dir"]).as_posix().endswith(
        "scout-api-camoufox-profiles/default"
    )
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

    item = ProductScrapeService(
        fetcher=FakeFetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=1,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=1,
        ),
    ).scrape(url)
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

    item = ProductScrapeService(
        fetcher=FakeFetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=1,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=1,
        ),
    ).scrape(url)
    assert item.store == "nissei"
    assert item.sku == "148321"
    assert item.price == Decimal("3227000")
