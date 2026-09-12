"""Amazon Brazil marketplace adapter tests."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.spiders.brazil.amazon import AmazonBrazilSpider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "amazon"
URL = "https://www.amazon.com.br/dp/B09WNK39JN"


def response_from_fixture(name: str, url: str = URL) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_amazon_br_offer_price_pix_installment_seller_and_currency() -> None:
    offer = AmazonBrazilSpider().extract_offer(
        response_from_fixture("br_available_pix_installment.html")
    )
    assert offer.store == "amazon"
    assert offer.country == "BR"
    assert offer.currency == "BRL"
    assert offer.product_id == offer.sku == "B09WNK39JN"
    assert offer.price == Decimal("349.00")
    assert offer.original_price == Decimal("449.00")
    assert offer.pix_price == Decimal("331.55")
    assert offer.installment_count == 10
    assert offer.installment_price == Decimal("34.90")
    assert offer.seller == "Amazon.com.br"
    assert offer.metadata["fulfilled_by"] == "Amazon.com.br"
    assert offer.available is True
    assert offer.metadata["pricing"]["pix_available"] is True
    assert offer.metadata["pricing"]["coupon_required"] is True
    assert offer.canonical_url == "https://www.amazon.com.br/dp/B09WNK39JN"


def test_amazon_br_marketplace_seller_and_fulfilled_by() -> None:
    offer = AmazonBrazilSpider().extract_offer(
        response_from_fixture(
            "br_marketplace_seller.html",
            "https://www.amazon.com.br/dp/B0BBWH6RKF",
        )
    )
    assert offer.seller == "TechShop BR"
    assert offer.metadata["fulfilled_by"] == "Amazon.com.br"
    assert offer.pix_price == Decimal("408.40")


def test_amazon_br_out_of_stock() -> None:
    offer = AmazonBrazilSpider().extract_offer(
        response_from_fixture(
            "br_out_of_stock.html",
            "https://www.amazon.com.br/dp/B0D1XD1ZV3",
        )
    )
    assert offer.availability == "out_of_stock"
    assert offer.available is False
    assert offer.currency == "BRL"


def test_amazon_br_details_variant_and_images() -> None:
    spider = AmazonBrazilSpider()
    response = response_from_fixture("br_available_pix_installment.html")
    details = spider.extract_details(response)
    assert details.product_id == "B09WNK39JN"
    assert "Echo Pop" in details.title
    assert details.brand == "Amazon"
    assert details.variant == "cor: Carvão"
    assert details.images == []
    images = spider.extract_images(response)
    assert images[0].startswith("https://m.media-amazon.com/images/")


def test_amazon_br_live_captured_buybox_fixtures() -> None:
    """Sanitized captures from live HTTP-first BR PDPs with Buy Box present."""
    spider = AmazonBrazilSpider()
    first = spider.extract_offer(
        response_from_fixture(
            "br_live_buybox_1.html",
            "https://www.amazon.com.br/dp/B0GY5SB1P3",
        )
    )
    assert first.country == "BR"
    assert first.currency == "BRL"
    assert first.product_id == "B0GY5SB1P3"
    assert first.price == Decimal("19.99")
    assert first.seller == "Danet Store"
    assert first.available is True
    assert first.canonical_url == "https://www.amazon.com.br/dp/B0GY5SB1P3"

    second = spider.extract_offer(
        response_from_fixture(
            "br_live_buybox_2.html",
            "https://www.amazon.com.br/dp/B0GN4S2ZSK",
        )
    )
    assert second.product_id == "B0GN4S2ZSK"
    assert second.price == Decimal("29.90")
    assert second.seller == "ALX Hub"
    assert second.available is True


def test_amazon_br_full_scrape_only_calls_gallery_when_requested(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    spider = AmazonBrazilSpider()
    images = MagicMock(wraps=spider.extract_images)
    spider.extract_images = images
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    class Fetcher:
        def fetch(self, _url: str) -> HtmlResponse:
            return response_from_fixture("br_available_pix_installment.html")

    service = ProductScrapeService(
        fetcher=Fetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=0,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=0,
        ),
    )
    service.scrape(URL, include_images=False)
    images.assert_not_called()
    service.scrape(URL, include_images=True)
    images.assert_called_once()
