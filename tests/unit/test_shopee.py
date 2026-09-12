import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scrapy.http import HtmlResponse, Request, TextResponse

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.spiders.brazil.shopee import ShopeeSpider
from scout_api.modules.crawler.spiders.registry import resolve_store_spider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "shopee"

PALIT_URL = (
    "https://shopee.com.br/Placa-de-Video-GeForce-NVIDIA-PALIT-RTX5070TI-16GB-"
    "GAMINGPRO-S-GDR7-256BIT-3-DP-HD-i.1293222703.58215350823"
    "?extraParams=%7B%22display_model_id%22%3A189624958952%2C%22model_selection_logic%22%3A3%7D"
)
PALIT_RTX5060_URL = (
    "https://shopee.com.br/Placa-de-Video-NVIDIA-GeForce-PALIT-RTX5060-8GB-"
    "INFINITY-2-OC-GDDR7-0120111-01-i.344381236.54358077814"
    "?extraParams=%7B%22display_model_id%22%3A355718024627%2C%22model_selection_logic%22%3A3%7D"
    "&sp_atk=tracking&xptdk=session"
)
KINGSTON_URL = (
    "https://shopee.com.br/Kingston-HyperX-Fury-DDR4-PC-RAM-4-Gb-8-16-DDR4-"
    "2133-2400-2666-3200-Mhz-Mem%C3%B3ria-De-Mesa-i.341936748.29277977480"
)
KINGSTON_MODEL_URL = KINGSTON_URL + "?model_id=10003"
OOS_URL = "https://shopee.com.br/produto-i.222.111"


def _html(name: str, url: str) -> HtmlResponse:
    body = (FIXTURES / name).read_bytes()
    return HtmlResponse(url, body=body, encoding="utf-8", request=Request(url))


def test_resolve_shopee_spider() -> None:
    spider = resolve_store_spider(KINGSTON_URL)
    assert isinstance(spider, ShopeeSpider)


def test_palit_offer_uses_display_model_not_cheapest() -> None:
    offer = ShopeeSpider().extract_offer(
        _html("product_palit_display_model.html", PALIT_URL)
    )
    assert offer.product_id == "58215350823"
    assert offer.sku == "189624958952"
    assert offer.metadata["shop_id"] == "1293222703"
    assert offer.metadata["model_id"] == "189624958952"
    assert offer.price == Decimal("8999.00")
    assert offer.original_price == Decimal("9999.00")
    assert offer.discount_percentage == Decimal("10.00")
    assert offer.installment_count == 10
    assert offer.installment_price == Decimal("899.90")
    assert offer.seller == "Loja Oficial PALIT BR"
    assert offer.available is True
    assert offer.metadata["source"]["price"] == "selected-model"


def test_palit_details_and_images() -> None:
    spider = ShopeeSpider()
    response = _html("product_palit_display_model.html", PALIT_URL)
    details = spider.extract_details(response)
    assert details.title.startswith("Placa de Video")
    assert details.brand == "PALIT"
    assert details.model == "RTX 5070 Ti"
    assert details.gtin == "4710568870011"
    assert details.variant == "Modelo: GAMINGPRO OC"
    assert details.images == []
    assert spider.supports_images is False
    assert spider.extract_images(response) == []
    # Gallery parser retained for fixtures/debug; not used in the live cost path.
    payload = spider._pdp_payload(response)
    item = spider._item(payload)
    model = spider._selected_model(
        item, payload, response.url, spider._url_identity(response.url)
    )
    images = spider._gallery_urls(payload, item, model)
    assert images[0].endswith("br-11134207-7r98o-palit-oc")
    assert "br-11134207-7r98o-palit-main" in images[1]
    assert all(
        "banner" not in url and "review" not in url and "avatar" not in url
        for url in images
    )


def test_kingston_without_model_picks_first_sellable_not_lowest() -> None:
    """4GB OOS is cheaper; default must be first in-stock model (8GB/2666)."""
    offer = ShopeeSpider().extract_offer(
        _html("product_kingston_variants.html", KINGSTON_URL)
    )
    assert offer.product_id == "29277977480"
    assert offer.metadata["shop_id"] == "341936748"
    assert offer.sku == "10002"
    assert offer.metadata["model_id"] == "10002"
    assert offer.price == Decimal("1599.00")
    assert offer.price != Decimal("899.00")
    assert offer.seller == "Kingston Official Store"
    assert offer.available is True

    details = ShopeeSpider().extract_details(
        _html("product_kingston_variants.html", KINGSTON_URL)
    )
    assert details.variant == "Capacidade: 8GB; Frequência: 2666MHz"
    assert details.brand == "Kingston"
    assert details.model == "HyperX Fury"


def test_kingston_explicit_model_id_query() -> None:
    offer = ShopeeSpider().extract_offer(
        _html("product_kingston_variants.html", KINGSTON_MODEL_URL)
    )
    assert offer.sku == "10003"
    assert offer.price == Decimal("1799.00")
    details = ShopeeSpider().extract_details(
        _html("product_kingston_variants.html", KINGSTON_MODEL_URL)
    )
    assert details.variant == "Capacidade: 8GB; Frequência: 3200MHz"


def test_out_of_stock_model() -> None:
    offer = ShopeeSpider().extract_offer(_html("product_out_of_stock.html", OOS_URL))
    assert offer.available is False
    assert offer.availability == "out_of_stock"


def test_blocked_error_raises_upstream_blocked() -> None:
    body = (FIXTURES / "blocked_90309999.json").read_bytes()
    response = TextResponse(
        KINGSTON_URL,
        body=body,
        encoding="utf-8",
        request=Request(KINGSTON_URL),
    )
    with pytest.raises(RequestError) as exc:
        ShopeeSpider().extract_offer(response)
    assert exc.value.code == "UPSTREAM_BLOCKED"


def test_include_images_gate(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    spider = ShopeeSpider()
    images = MagicMock(wraps=spider.extract_images)
    spider.extract_images = images
    monkeypatch.setattr(
        "scout_api.modules.crawler.services.product_scrape_service.resolve_store_spider",
        lambda _url: spider,
    )

    class Fetcher:
        def fetch(self, _url: str) -> HtmlResponse:
            return _html("product_kingston_variants.html", KINGSTON_URL)

    service = ProductScrapeService(
        fetcher=Fetcher(),
        guard=ScrapeGuard(
            url_cooldown_seconds=0,
            domain_min_interval_seconds=0,
            result_cache_ttl_seconds=0,
        ),
    )
    without = service.scrape(KINGSTON_URL, include_images=False)
    images.assert_not_called()
    assert without.images == []

    with_images = service.scrape(KINGSTON_URL, include_images=True)
    # Shopee store-cost policy: supports_images=False skips extract_images.
    images.assert_not_called()
    assert with_images.images == []
    assert with_images.metadata.get("images_omitted") == "store-cost-policy"


def test_palit_price_detail_extracts_pix_coupon_and_installment() -> None:
    """Selected-model list price must not skip get_pc final/Pix breakdown."""
    offer = ShopeeSpider().extract_offer(
        _html("product_palit_price_detail.html", PALIT_RTX5060_URL)
    )

    assert offer.product_id == "54358077814"
    assert offer.sku == "355718024627"
    assert offer.metadata["model_id"] == "355718024627"
    assert offer.metadata["display_model_id"] == "355718024627"

    assert offer.original_price == Decimal("5999.00")
    assert offer.price == Decimal("3699.00")
    assert offer.pix_price == Decimal("3380.08")

    pricing = offer.metadata["pricing"]
    assert pricing["product_discount"] == "2300.00"
    assert pricing["coupon_discount"] == "25.00"
    assert pricing["pix_discount"] == "293.92"
    assert pricing["pix_requires_coupon"] is True
    assert "cupom" in pricing["final_price_hint"].casefold()

    # Consistency checks against the Shopee card (values come from payload).
    assert offer.original_price - Decimal(pricing["product_discount"]) == offer.price
    assert (
        offer.price
        - Decimal(pricing["coupon_discount"])
        - Decimal(pricing["pix_discount"])
        == offer.pix_price
    )

    assert offer.installment_count == 12
    assert offer.installment_price == Decimal("306.17")

    source = offer.metadata["source"]
    assert source["price"] == "selected-model"
    assert source["original_price"] == "selected-model-before-discount"
    assert source["pix_price"] == "product-price-final"
    assert source["product_discount"] == "price-breakdown"
    assert source["coupon_discount"] == "price-breakdown"
    assert source["pix_discount"] == "price-breakdown"
    assert source["installment"] == "product-price-recommended-plan"

    assert "sp_atk" not in offer.canonical_url
    assert "xptdk" not in offer.canonical_url
    assert "display_model_id" in offer.canonical_url


def test_selected_model_price_does_not_skip_pix_lookup() -> None:
    """Regression: finding selected-model.price must still consult final pricing."""
    offer = ShopeeSpider().extract_offer(
        _html("product_palit_price_detail.html", PALIT_RTX5060_URL)
    )
    assert offer.metadata["source"]["price"] == "selected-model"
    assert offer.pix_price is not None
    assert offer.pix_price < offer.price


def test_final_pricing_ignored_when_breakdown_belongs_to_other_model() -> None:
    """Do not attach Pix/coupon breakdown from a different featured model_id."""
    payload = json.loads(
        (FIXTURES / "get_pc_palit_price_detail.json").read_text(encoding="utf-8")
    )
    data = payload["data"]
    data["product_price"]["final_price_info"]["model_id"] = 999999999
    body = (
        '<!DOCTYPE html><html><body><script type="application/json" '
        'data-shopee-pdp="1">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script></body></html>"
    )
    response = HtmlResponse(
        PALIT_RTX5060_URL,
        body=body.encode("utf-8"),
        encoding="utf-8",
        request=Request(PALIT_RTX5060_URL),
    )
    offer = ShopeeSpider().extract_offer(response)
    assert offer.price == Decimal("3699.00")
    assert offer.pix_price is None
    assert offer.metadata["source"]["pix_price"] == "not-found-other-model"
    assert "pricing" not in offer.metadata
