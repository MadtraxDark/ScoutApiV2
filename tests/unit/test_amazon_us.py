"""Amazon United States marketplace adapter tests."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.spiders.brazil.amazon import AmazonBrazilSpider
from scout_api.modules.crawler.spiders.usa.amazon import AmazonUSSpider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "amazon"
URL = "https://www.amazon.com/dp/B09WNK39JN"


def response_from_fixture(name: str, url: str = URL) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_amazon_us_offer_buybox_list_price_seller_and_currency() -> None:
    offer = AmazonUSSpider().extract_offer(
        response_from_fixture("us_available_amazon_sold.html")
    )
    assert offer.store == "amazon"
    assert offer.country == "US"
    assert offer.currency == "USD"
    assert offer.product_id == offer.sku == "B09WNK39JN"
    assert offer.price == Decimal("39.99")
    assert offer.original_price == Decimal("59.99")
    assert offer.pix_price is None
    assert offer.seller == "Amazon.com"
    assert offer.metadata["fulfilled_by"] == "Amazon.com"
    assert offer.available is True
    assert offer.metadata["shipping_to_brazil"] is False
    assert offer.metadata["pricing"]["coupon_required"] is True
    assert offer.metadata["pricing"]["prime_badge"] is True
    assert offer.canonical_url == "https://www.amazon.com/dp/B09WNK39JN"


def test_amazon_us_marketplace_seller_fulfilled_by_amazon() -> None:
    offer = AmazonUSSpider().extract_offer(
        response_from_fixture(
            "us_marketplace_seller.html",
            "https://www.amazon.com/dp/B014I8SIJY",
        )
    )
    assert offer.seller == "CableWorld LLC"
    assert offer.metadata["fulfilled_by"] == "Amazon.com"
    assert offer.price == Decimal("6.99")


def test_amazon_us_does_not_use_monthly_payment_as_price() -> None:
    offer = AmazonUSSpider().extract_offer(
        response_from_fixture(
            "us_subscribe_prime_coupon.html",
            "https://www.amazon.com/dp/B09477MZT5",
        )
    )
    assert offer.price == Decimal("24.99")
    assert offer.original_price == Decimal("29.99")
    assert offer.installment_price is None
    assert offer.metadata["pricing"]["subscribe_and_save"] is True
    assert offer.metadata["pricing"]["coupon_required"] is True


def test_amazon_us_details_keep_selected_variant() -> None:
    details = AmazonUSSpider().extract_details(
        response_from_fixture("us_available_amazon_sold.html")
    )
    assert details.variant == "color: Charcoal; configuration: Device only"
    assert details.brand == "Amazon"
    assert details.model == "Echo Pop"


def test_amazon_us_images_use_official_gallery_only() -> None:
    spider = AmazonUSSpider()
    response = response_from_fixture("us_available_amazon_sold.html")
    assert spider.extract_details(response).images == []
    images = spider.extract_images(response)
    assert len(images) >= 1
    assert all("media-amazon.com" in url for url in images)


def test_cross_market_same_asin_keeps_independent_offers() -> None:
    us = AmazonUSSpider().extract_offer(
        response_from_fixture(
            "cross_market_us.html",
            "https://www.amazon.com/dp/B07G4MNFS1",
        )
    )
    br = AmazonBrazilSpider().extract_offer(
        response_from_fixture(
            "cross_market_br.html",
            "https://www.amazon.com.br/dp/B07G4MNFS1",
        )
    )
    assert us.product_id == br.product_id == "B07G4MNFS1"
    assert us.currency == "USD" and br.currency == "BRL"
    assert us.price == Decimal("226.14")
    assert br.price == Decimal("1599.00")
    assert us.price != br.price
    assert us.country == "US" and br.country == "BR"
    assert us.seller != br.seller or us.currency != br.currency


def test_amazon_us_full_scrape_only_calls_gallery_when_requested(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    spider = AmazonUSSpider()
    images = MagicMock(wraps=spider.extract_images)
    spider.extract_images = images
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    class Fetcher:
        def fetch(self, _url: str) -> HtmlResponse:
            return response_from_fixture("us_available_amazon_sold.html")

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
