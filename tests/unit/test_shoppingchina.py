from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.services.store_resolver import resolve_store_spider
from scout_api.modules.crawler.spiders.paraguay.shoppingchina import ShoppingChinaSpider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "shoppingchina"
URL = (
    "https://www.shoppingchina.com.br/produto/"
    "celular-apple-iphone-15-128gb-blue-sim-883614"
)
PY_URL = (
    "https://www.shoppingchina.com.py/producto/"
    "celular-apple-iphone-15-128gb-blue-sim-883614"
)


def response_from_fixture(name: str, url: str = PY_URL) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_shoppingchina_domains_resolve_to_spider() -> None:
    assert isinstance(resolve_store_spider(URL), ShoppingChinaSpider)
    assert isinstance(resolve_store_spider(PY_URL), ShoppingChinaSpider)


def test_shoppingchina_keeps_requested_host() -> None:
    spider = ShoppingChinaSpider()
    assert spider.prepare_fetch_url(URL) == URL
    assert spider.prepare_fetch_url(PY_URL) == PY_URL


def test_shoppingchina_py_rewrites_legacy_produto_path() -> None:
    spider = ShoppingChinaSpider()
    legacy = (
        "https://www.shoppingchina.com.py/produto/"
        "celular-apple-iphone-16-a3287-128gb-black-sim-948623"
    )
    assert spider.prepare_fetch_url(legacy) == (
        "https://www.shoppingchina.com.py/producto/"
        "celular-apple-iphone-16-a3287-128gb-black-sim-948623"
    )
    # BR locale keeps Portuguese path.
    assert spider.prepare_fetch_url(URL) == URL


def test_shoppingchina_quick_search_rewrites_produto_urls() -> None:
    spider = ShoppingChinaSpider()
    body = (
        '[{"url_po":"/produto/celular-apple-iphone-16-a3287-128gb-black-sim-948623",'
        '"title_po":"CELULAR APPLE IPHONE 16 A3287 128GB BLACK SIM"}]'
    )
    response = HtmlResponse(
        "https://www.shoppingchina.com.py/quick_search?search=iphone",
        body=body.encode(),
        encoding="utf-8",
        request=Request("https://www.shoppingchina.com.py/quick_search?search=iphone"),
    )
    candidates = spider.parse_search_results(response)
    assert len(candidates) == 1
    assert "/producto/" in candidates[0].url
    assert "/produto/" not in candidates[0].url
    assert candidates[0].product_id == "948623"
    assert candidates[0].title and "IPHONE 16" in candidates[0].title.upper()


def test_shoppingchina_soft_404_title_is_parse_error() -> None:
    from scout_api.modules.crawler.core.exceptions import ParseError

    spider = ShoppingChinaSpider()
    response = HtmlResponse(
        "https://www.shoppingchina.com.py/produto/missing-1",
        body=b"<!DOCTYPE html><html><head><title>Error 404 | Shopping China"
        b"</title></head><body></body></html>",
        encoding="utf-8",
        request=Request("https://www.shoppingchina.com.py/produto/missing-1"),
    )
    try:
        spider.extract_offer(response)
    except ParseError as exc:
        assert "não encontrado" in str(exc).casefold()
        return
    raise AssertionError("expected ParseError")


def test_shoppingchina_offer_identity_price_currency_and_seller() -> None:
    offer = ShoppingChinaSpider().extract_offer(
        response_from_fixture("product_available.html")
    )
    assert offer.store == "shoppingchina"
    assert offer.country == "PY"
    assert offer.product_id == "883614"
    assert offer.sku == "883614"
    assert offer.seller == "Shopping China"
    assert offer.currency == "PYG"
    assert offer.price == Decimal("4433000")
    assert offer.original_price is None
    assert offer.discount_percentage is None
    assert offer.available is True
    assert offer.availability == "available"
    assert offer.metadata["display_prices"]["USD"] == "650.00"
    assert offer.metadata["internal_product_id"] == "78094"
    assert offer.metadata["shipping_to_brazil"] is False
    assert offer.canonical_url.endswith("883614")


def test_shoppingchina_br_reference_url_uses_visible_brl() -> None:
    """``.com.br`` advertises R$ as the primary tax-free/tourism price."""
    offer = ShoppingChinaSpider().extract_offer(
        response_from_fixture(
            "product_br_locale_no_brazil_shipping.html",
            url=URL,
        )
    )
    assert offer.country == "PY"
    assert offer.currency == "BRL"
    assert offer.price == Decimal("3406.00")
    assert offer.metadata["source"]["price"] == "rendered-primary-price"
    assert offer.metadata["display_prices"]["USD"] == "650.00"
    assert offer.available is True
    assert offer.metadata["shipping_to_brazil"] is False


def test_shoppingchina_details_specs_variant_gtin_and_images() -> None:
    spider = ShoppingChinaSpider()
    response = response_from_fixture("product_available.html")
    details = spider.extract_details(response)
    assert details.product_id == "883614"
    assert details.sku == "883614"
    assert details.gtin == "195949036453"
    assert details.brand == "Apple"
    assert details.model == "iPhone 15"
    assert details.variant == "color: Blue; storage: 128 GB"
    assert details.specifications["Tela"] == "Super Retina XDR de 6,1 polegadas"
    assert details.specifications["storage"] == "128 GB"
    assert details.metadata["source"]["brand"] == "structured-data"
    assert details.metadata["source"]["color"] == "product-specifications"
    assert details.metadata["source"]["model"] == "product-specifications"
    assert details.metadata["source"]["storage"] == "product-title-fallback"
    assert "iPhone 15 redefine" in (details.description or "")
    assert spider.extract_images(response) == [
        "https://www.shoppingchina.com.py/rails/active_storage/blobs/redirect/eyJtest/883614.jpg",
        "https://www.shoppingchina.com.py/rails/active_storage/blobs/redirect/eyJtest/883614-side.jpg",
    ]


def test_shoppingchina_discount_keeps_price_and_currency_aligned() -> None:
    offer = ShoppingChinaSpider().extract_offer(
        response_from_fixture(
            "product_discount.html",
            url="https://www.shoppingchina.com.py/producto/depilador-philips-bre740-10-1000195",
        )
    )
    assert offer.currency == "PYG"
    assert offer.price == Decimal("1197000")
    assert offer.original_price == Decimal("1330000")
    assert offer.discount_percentage == Decimal("10.00")
    assert offer.metadata["display_prices"]["USD"] == "175.50"
    # Never mix USD amount into PYG price.
    assert offer.price != Decimal("175.50")


def test_shoppingchina_no_brazil_shipping_does_not_mark_unavailable() -> None:
    """BR locale without cart / Brazil shipping must not flip available=false."""
    offer = ShoppingChinaSpider().extract_offer(
        response_from_fixture(
            "product_br_locale_no_brazil_shipping.html",
            url=URL,
        )
    )
    assert offer.price == Decimal("3406.00")
    assert offer.currency == "BRL"
    assert offer.available is True
    assert offer.availability == "available"
    assert offer.metadata["shipping_to_brazil"] is False
    assert offer.metadata["display_prices"]["USD"] == "650.00"
    assert offer.metadata["source"]["availability"] in {
        "json-ld-availability",
        "active-offer-price",
    }


def test_shoppingchina_out_of_stock_is_not_available() -> None:
    item = ShoppingChinaSpider().parse_product(
        response_from_fixture(
            "product_out_of_stock.html",
            url="https://www.shoppingchina.com.py/producto/producto-agotado-demo-555001",
        )
    )
    assert item.available is False
    assert item.availability == "out_of_stock"
    assert item.price == Decimal("100000")
    assert item.currency == "PYG"


def test_shoppingchina_full_scrape_only_calls_gallery_when_requested(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    spider = ShoppingChinaSpider()
    images = MagicMock(wraps=spider.extract_images)
    spider.extract_images = images
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    class Fetcher:
        def fetch(self, _url: str) -> HtmlResponse:
            return response_from_fixture("product_available.html")

    service = ProductScrapeService(
        fetcher=Fetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=0,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=0,
        ),
    )
    service.scrape(PY_URL, include_images=False)
    images.assert_not_called()

    service.scrape(PY_URL, include_images=True)
    images.assert_called_once()
