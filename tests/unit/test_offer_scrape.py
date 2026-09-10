from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.models.product import ProductOffer
from scout_api.modules.crawler.services.offer_scrape_service import OfferScrapeService
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.spiders.brazil.magazineluiza import MagazineLuizaSpider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "magazineluiza"


def _response_from_fixture(name: str) -> HtmlResponse:
    url = (
        "https://www.magazineluiza.com.br/p/240590700/ga/gap5/?seller_id=magazineluiza"
    )
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_magalu_extract_offer_returns_commercial_fields() -> None:
    offer = MagazineLuizaSpider().extract_offer(
        _response_from_fixture("product_structured_offer.html")
    )
    assert isinstance(offer, ProductOffer)
    assert offer.product_id == "aebh5a7a94"
    assert offer.sku == "989702"
    assert offer.seller == "kabum"
    assert offer.price == Decimal("5058.85")
    assert offer.pix_price == Decimal("4805.91")
    assert offer.original_price == Decimal("5288.85")
    assert offer.discount_percentage == Decimal("5.00")
    assert offer.installment_count == 10
    assert offer.installment_price == Decimal("505.89")
    assert offer.availability == "available"
    assert offer.available is True
    dumped = offer.model_dump()
    assert "title" not in dumped
    assert "brand" not in dumped
    assert "model" not in dumped
    assert "gtin" not in dumped
    assert "description" not in dumped
    assert "images" not in dumped


def test_magalu_extract_offer_does_not_require_details_fields() -> None:
    offer = MagazineLuizaSpider().extract_offer(
        _response_from_fixture("product_available.html")
    )
    assert offer.price == Decimal("4399.00")
    assert offer.pix_price == Decimal("4399.00")
    assert offer.seller == "magazineluiza"
    assert offer.available is True


def test_offer_scrape_service_skips_extract_details(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    url = "https://www.magazineluiza.com.br/p/240590700"
    html = _response_from_fixture("product_structured_offer.html")

    class FakeFetcher:
        def fetch(self, fetch_url: str) -> HtmlResponse:
            return html

    spider = MagazineLuizaSpider()
    details_mock = MagicMock(wraps=spider.extract_details)
    monkeypatch.setattr(spider, "extract_details", details_mock)
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.offer_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    offer = OfferScrapeService(
        fetcher=FakeFetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=1,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=1,
        ),
    ).scrape_offer(url)

    assert offer.price == Decimal("5058.85")
    assert offer.seller == "kabum"
    details_mock.assert_not_called()


def test_product_scrape_service_composes_offer_and_details(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    url = "https://www.magazineluiza.com.br/p/aebh5a7a94"
    html = _response_from_fixture("product_structured_offer.html")

    class FakeFetcher:
        def fetch(self, fetch_url: str) -> HtmlResponse:
            return html

    spider = MagazineLuizaSpider()
    offer_mock = MagicMock(wraps=spider.extract_offer)
    details_mock = MagicMock(wraps=spider.extract_details)
    monkeypatch.setattr(spider, "extract_offer", offer_mock)
    monkeypatch.setattr(spider, "extract_details", details_mock)
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    item = ProductScrapeService(
        fetcher=FakeFetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=1,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=1,
        ),
    ).scrape(url)

    offer_mock.assert_called_once()
    details_mock.assert_called_once()
    assert item.title  # from details
    assert item.brand == "Sony"
    assert item.price == Decimal("5058.85")
    assert item.seller == "kabum"
