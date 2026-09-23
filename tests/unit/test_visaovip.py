from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import ParseError
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.services.store_resolver import resolve_store_spider
from scout_api.modules.crawler.spiders.paraguay.visaovip import VisaoVipSpider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "visaovip"
URL = (
    "https://visaovip.com/prod/placas-de-video-nvidia/"
    "placa-de-video-msi-shadow-3x-oc-12gb-geforce-rtx5070-gddr7-912-v532-232/55359/"
)
DISCOUNT_URL = (
    "https://visaovip.com/prod/placas-mae-intel/"
    "placa-mae-gigabyte-b860m-k-gen5-socket-lga-1851-ddr5/59771/"
)
PHONE_URL = (
    "https://visaovip.com/prod/smartphones-e-celulares/"
    "celular-motorola-g17-xt2623-1-4gb-de-ram-128gb-tela-6-72-dual-sim-lte-"
    "pantone-bordeaux-rosa/60039/"
)
WATCH_URL = (
    "https://visaovip.com/prod/smartwatch/"
    "relogio-smartwatch-realme-watch-s5-rmw2502-rock-cinza/59715/"
)


def response_from_fixture(name: str, url: str = URL) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_visaovip_domain_resolves_to_spider() -> None:
    spider = resolve_store_spider(URL)
    assert isinstance(spider, VisaoVipSpider)
    assert spider.store == "visaovip"
    assert spider.country == "PY"
    assert spider.currency == "USD"


def test_visaovip_offer_identity_price_and_availability() -> None:
    offer = VisaoVipSpider().extract_offer(
        response_from_fixture("product_available.html")
    )
    assert offer.product_id == "55359"
    assert offer.sku == "912-V532-232"
    assert offer.seller == "Visaovip"
    assert offer.currency == "USD"
    assert offer.price == Decimal("889.00")
    assert offer.original_price is None
    assert offer.pix_price is None
    assert offer.discount_percentage is None
    assert offer.installment_count is None
    assert offer.installment_price is None
    assert offer.available is True
    assert offer.availability == "available"
    assert offer.canonical_url.endswith("55359")
    assert offer.metadata["shipping_to_brazil"] is False
    assert offer.metadata["source"]["price"] == "product-price-state"
    assert offer.metadata["source"]["availability"] == "product-balance-state"
    assert offer.metadata["source"]["sku"] == "product-specifications"


def test_visaovip_discount_uses_promotion_as_current_price() -> None:
    offer = VisaoVipSpider().extract_offer(
        response_from_fixture("product_discount.html", DISCOUNT_URL)
    )
    assert offer.product_id == "59771"
    assert offer.price == Decimal("91.00")
    assert offer.original_price == Decimal("98.00")
    assert offer.discount_percentage == Decimal("7.14")
    assert offer.metadata["source"]["price"] == "product-promotion-price"
    assert offer.metadata["source"]["original_price"] == "product-price-state"


def test_visaovip_details_brand_model_specs_and_title_fallback_reuse() -> None:
    details = VisaoVipSpider().extract_details(
        response_from_fixture("product_available.html")
    )
    assert details.product_id == "55359"
    assert details.sku == "912-V532-232"
    assert details.gtin is None
    assert "MSI Shadow 3X OC" in details.title
    assert details.brand == "MSI"
    assert details.model == "GeForce RTX 5070"
    assert details.variant == "Shadow 3X OC"
    assert details.specifications["MARCA"] == "MSI"
    assert details.specifications["REFERÊNCIA"] == "912-V532-232"
    assert details.specifications["MEMÓRIA V-RAM"] == "12 GB"
    assert details.specifications.get("vram") == "12 GB"
    assert details.specifications.get("gpu_model") is not None
    assert details.metadata["source"]["category"] == "gpu"
    assert details.images == []
    # Color-less GPU: no commercial variant dimensions.
    assert details.variant is None or "bits" not in details.variant


def test_visaovip_other_categories_parse() -> None:
    phone = VisaoVipSpider().extract_details(
        response_from_fixture("product_phone.html", PHONE_URL)
    )
    assert phone.product_id == "60039"
    assert phone.brand == "MOTOROLA"
    assert "Motorola" in phone.title

    watch_offer = VisaoVipSpider().extract_offer(
        response_from_fixture("product_watch.html", WATCH_URL)
    )
    assert watch_offer.product_id == "59715"
    assert watch_offer.price == Decimal("82.90")
    assert watch_offer.original_price == Decimal("88.00")


def test_visaovip_images_gallery_official_only() -> None:
    spider = VisaoVipSpider()
    images = spider.extract_images(response_from_fixture("product_available.html"))
    assert images[0].startswith("https://cdn.visaovip.com/img/prod/")
    assert all("cdn.visaovip.com/img/prod/" in url for url in images)
    assert all("/marca/" not in url for url in images)
    assert len(images) == 4
    assert len(images) == len(set(images))


def test_visaovip_full_scrape_only_calls_gallery_when_requested(
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    spider = VisaoVipSpider()
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
    service.scrape(URL, include_images=False)
    images.assert_not_called()

    service.scrape(URL, include_images=True)
    images.assert_called_once()


def test_visaovip_out_of_stock_from_balance_flag() -> None:
    offer = VisaoVipSpider().extract_offer(
        response_from_fixture("product_out_of_stock.html")
    )
    assert offer.product_id == "55359"
    assert offer.available is False
    assert offer.availability == "out_of_stock"
    assert offer.metadata["source"]["availability"] == "product-balance-state"


def test_visaovip_soft_404_is_parse_error_not_unavailable() -> None:
    spider = VisaoVipSpider()
    response = response_from_fixture(
        "product_soft_404.html",
        "https://visaovip.com/prod/memoria-ram/missing/51563/",
    )
    with pytest.raises(ParseError, match="soft-404"):
        spider.extract_offer(response)


def test_visaovip_build_search_url_uses_termo_slug() -> None:
    spider = VisaoVipSpider()
    assert spider.supports_search is True
    url = spider.build_search_url("ASUS TUF Gaming B650M-E WIFI")
    assert url == (
        "https://www.visaovip.com/busca/termo/ASUS-TUF-Gaming-B650M-E-WIFI/"
    )
    # Hyphenated model tokens survive whitespace→hyphen slugification.
    assert "B650M-E" in url
    assert "?q=" not in url


def test_visaovip_parse_search_results_extracts_product_cards() -> None:
    spider = VisaoVipSpider()
    response = response_from_fixture(
        "search_termo_board.html",
        "https://www.visaovip.com/busca/termo/ASUS-TUF-Gaming-B650M-E-WIFI/",
    )
    candidates = spider.parse_search_results(response)
    assert len(candidates) == 2
    assert candidates[0].product_id == "41749"
    assert candidates[0].url.endswith("/41749/")
    assert "B650M-E" in (candidates[0].title or "")
    assert "U$" not in (candidates[0].title or "")
    assert "Placas Mãe" not in (candidates[0].title or "")
    assert candidates[1].product_id == "54574"
    # CDN image path must not appear as a candidate.
    assert all("/595465" not in (c.url or "") for c in candidates)


def test_visaovip_motherboard_details_identity_and_usd_price() -> None:
    spider = VisaoVipSpider()
    url = (
        "https://www.visaovip.com/prod/placas-mae-amd/"
        "placa-mae-asus-tuf-gaming-b650m-e-wi-fi-socket-am5-ddr5/41749/"
    )
    response = response_from_fixture("product_motherboard.html", url)
    details = spider.extract_details(response)
    offer = spider.extract_offer(response)
    assert details.product_id == "41749"
    assert "B650M-E" in details.title.upper().replace(" ", "")
    assert (details.brand or "").upper() == "ASUS"
    assert offer.currency == "USD"
    assert offer.price > 0
    assert offer.available is True
    assert details.sku  # manufacturer REFERÊNCIA when present
