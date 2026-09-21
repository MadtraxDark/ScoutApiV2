"""Magazine Luiza gallery extraction — media.images vs JSON-LD single image."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.spiders.brazil.magazineluiza import MagazineLuizaSpider
from scout_api.modules.crawler.stores import STORE_CONFIGS

FIXTURES = Path(__file__).parents[1] / "fixtures" / "magazineluiza"
GALLERY_URL = (
    "https://www.magazineluiza.com.br/apple-iphone-15-128gb-preto-61-48mp-ios-5g/"
    "p/238035600/te/ip15/"
)


def _response(name: str, url: str = GALLERY_URL) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_magalu_media_images_returns_full_gallery_not_json_ld_only() -> None:
    spider = MagazineLuizaSpider()
    images = spider.extract_images(_response("product_gallery_media.html"))

    assert len(images) >= 2
    assert images[0].endswith("69da101a0dddad57e820c0b0bde148d8.jpg")
    assert all("/238035600/" in url for url in images)
    assert all("1200x1200" in url for url in images)
    # Distinct asset hashes — not collapsed into one URL.
    hashes = {url.rsplit("/", 1)[-1] for url in images}
    assert len(hashes) == len(images)
    assert len(hashes) > 1


def test_magalu_dedupe_keeps_distinct_assets_same_resolution_slot() -> None:
    spider = MagazineLuizaSpider()
    a = (
        "https://a-static.mlcdn.com.br/450x450/prod/magazineluiza/238035600/"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg"
    )
    b = (
        "https://a-static.mlcdn.com.br/1200x1200/prod/magazineluiza/238035600/"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg"
    )
    c = (
        "https://a-static.mlcdn.com.br/1200x1200/prod/magazineluiza/238035600/"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.jpg"
    )
    # Prefer first occurrence (main) when identity matches.
    out = spider._dedupe_gallery_preserve_order([b, c], main_url=a)
    assert out == [a, c]


def test_magalu_include_images_false_skips_extract_images(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    spider = MagazineLuizaSpider()
    images = MagicMock(wraps=spider.extract_images)
    monkeypatch.setattr(spider, "extract_images", images)
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    class Fetcher:
        def fetch(self, _url: str) -> HtmlResponse:
            return _response("product_gallery_media.html")

    service = ProductScrapeService(
        fetcher=Fetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=0,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=0,
        ),
    )
    item = service.scrape(GALLERY_URL, include_images=False)
    images.assert_not_called()
    assert item.images == []
    assert item.title


def test_magalu_include_images_true_calls_extract_and_sets_pipeline(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    spider = MagazineLuizaSpider()
    images = MagicMock(wraps=spider.extract_images)
    monkeypatch.setattr(spider, "extract_images", images)
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    class Fetcher:
        def fetch(self, _url: str) -> HtmlResponse:
            return _response("product_gallery_media.html")

    item = ProductScrapeService(
        fetcher=Fetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=0,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=0,
        ),
    ).scrape(GALLERY_URL, include_images=True)

    images.assert_called_once()
    assert len(item.images) >= 2
    pipeline = item.metadata.get("image_pipeline") or {}
    assert pipeline.get("images_found_raw", 0) >= 2
    assert pipeline.get("images_returned") == len(item.images)
    assert item.metadata.get("image_status") == "success"


def test_magalu_store_capability_defaults_images_on() -> None:
    config = STORE_CONFIGS["magazineluiza"]
    assert config.supports_images is True
    assert config.image_fetch_cost == "low"
    assert config.default_include_images is True
