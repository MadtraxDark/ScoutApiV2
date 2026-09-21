"""Timed promotion wiring for Shopee / ML / Terabyte / Pichau."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from scrapy.http import HtmlResponse, TextResponse

from scout_api.modules.crawler.spiders.brazil.mercadolivre import MercadoLivreSpider
from scout_api.modules.crawler.spiders.brazil.pichau import PichauSpider
from scout_api.modules.crawler.spiders.brazil.shopee import ShopeeSpider
from scout_api.modules.crawler.spiders.brazil.terabyteshop import TerabyteShopSpider
from scout_api.modules.crawler.stores import STORE_CONFIGS
from scout_api.modules.crawler.utils.timed_promotion import (
    mercadolivre_lightning_promotion,
    shopee_flash_promotion,
    terabyte_promotion_from_html,
)
from scout_api.modules.monitoring.extractors import extract_terabyte_countdown

ROOT = Path(__file__).resolve().parents[1]
SHOPEE_FIXTURE = ROOT / "fixtures" / "shopee" / "get_pc_palit_price_detail.json"
TERABYTE_HTML = ROOT.parent / "data" / "_terabyte_live.html"
PICHAU_HTML = ROOT.parent / "data" / "_pichau_probe.html"


def _text_response(
    url: str, body: str, *, content_type: str = "text/html"
) -> HtmlResponse:
    return HtmlResponse(
        url=url,
        body=body.encode("utf-8"),
        encoding="utf-8",
        headers={"Content-Type": content_type},
    )


def test_stores_pichau_terabyte_marked_implemented() -> None:
    assert STORE_CONFIGS["pichau"].implemented is True
    assert STORE_CONFIGS["terabyteshop"].implemented is True


def test_shopee_flash_sale_emits_metadata_promotion() -> None:
    payload = json.loads(SHOPEE_FIXTURE.read_text(encoding="utf-8"))
    data = payload["data"]
    # Fixture has flash_sale:null — inject a realistic timed flash sale.
    end = int(datetime(2026, 9, 22, 3, 0, tzinfo=UTC).timestamp())
    data["flash_sale"] = {
        "start_time": end - 3600,
        "end_time": end,
        "flash_sale_type": 1,
    }
    promo = shopee_flash_promotion(data, model_id="1", product_id="54358077814")
    assert promo is not None
    assert promo["type"] == "flash_sale"
    assert promo["expires_at"].startswith("2026-09-22T03:00:00")

    body = json.dumps({"error": None, "data": data})
    response = TextResponse(
        url="https://shopee.com.br/product/344381236/54358077814",
        body=body.encode("utf-8"),
        encoding="utf-8",
        headers={"Content-Type": "application/json"},
    )
    offer = ShopeeSpider().extract_offer(response)
    assert "promotion" in offer.metadata
    assert offer.metadata["promotion"]["expires_at"].startswith("2026-09-22")


def test_shopee_fixture_without_flash_has_no_promotion() -> None:
    body = SHOPEE_FIXTURE.read_text(encoding="utf-8")
    response = TextResponse(
        url="https://shopee.com.br/product/344381236/54358077814",
        body=body.encode("utf-8"),
        encoding="utf-8",
        headers={"Content-Type": "application/json"},
    )
    offer = ShopeeSpider().extract_offer(response)
    assert "promotion" not in offer.metadata


def test_mercadolivre_lightning_finish_date_metadata() -> None:
    html = (
        '"MLBU5083307469":{"free_shipping":true,"promotion_type":"TODAY_PROMOTION",'
        '"lightning_deal_configuration":{"finish_date":"2026-09-22T03:00:00Z"}}'
    )
    promo = mercadolivre_lightning_promotion(
        html, item_id="MLB5083307469", product_id="MLB27705742"
    )
    assert promo is not None
    assert promo["expires_at"] == "2026-09-22T03:00:00Z"
    assert promo["type"] == "lightning_deal"


def test_mercadolivre_spider_attaches_promotion_when_present() -> None:
    # Minimal valid JSON-LD PDP + lightning config for the selected item.
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Cam","sku":"MLB27705742","offers":{
      "@type":"Offer","price":"159.99","priceCurrency":"BRL",
      "availability":"https://schema.org/InStock"}}
    </script>
    </head><body>
    <h1 class="ui-pdp-title">Cam</h1>
    <script>
    {"MLB4540716592":{"lightning_deal_configuration":{"finish_date":"2026-09-22T03:00:00Z"}}}
    </script>
    </body></html>
    """
    url = (
        "https://www.mercadolivre.com.br/cam/p/MLB27705742"
        "?pdp_filters=item_id:MLB4540716592"
    )
    offer = MercadoLivreSpider().extract_offer(_text_response(url, html))
    assert offer.metadata.get("promotion", {}).get("expires_at") == (
        "2026-09-22T03:00:00Z"
    )


def test_terabyte_live_html_offer_and_promotion() -> None:
    if not TERABYTE_HTML.exists():
        # Fall back to minimal synthetic HTML with countdown.
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Product","name":"Monitor","sku":"41251","offers":'
            '{"price":"549.99","priceCurrency":"BRL",'
            '"availability":"https://schema.org/InStock",'
            '"priceValidUntil":"2026-09-28"}}</script>'
            "<script>$('#ctd41251').countdown('2026/09/28 10:00:59');</script>"
        )
        url = "https://www.terabyteshop.com.br/produto/41251/monitor"
    else:
        html = TERABYTE_HTML.read_text(encoding="utf-8")
        url = (
            "https://www.terabyteshop.com.br/produto/41251/"
            "monitor-gamer-gigabyte-gs24f14-238-pol-full-hd-ips-144hz-1ms-104srgb-hdmidp"
        )
    obs = extract_terabyte_countdown(html, product_id="41251")
    assert obs is not None
    promo = terabyte_promotion_from_html(html, product_id="41251")
    assert promo is not None
    offer = TerabyteShopSpider().extract_offer(_text_response(url, html))
    assert offer.product_id == "41251"
    assert offer.price == Decimal("549.99")
    assert "promotion" in offer.metadata
    assert offer.metadata["promotion"]["expires_at"]


def test_pichau_rsc_offer_without_timed_promotion() -> None:
    if PICHAU_HTML.exists():
        html = PICHAU_HTML.read_text(encoding="utf-8")
    else:
        html = (
            '<script type="application/ld+json">'
            '{"@type":"Product","name":"Fonte","offers":{"price":"705.87",'
            '"priceCurrency":"BRL","availability":"https://schema.org/InStock"}}'
            "</script>"
            '"product":{"id":54920,"sku":"CP-9020295-BR","name":"Fonte Corsair",'
            '"special_price":705.87,"pichau_prices":{"avista":599.99,'
            '"avista_discount":15,"avista_method":"PIX","base_price":941.16,'
            '"final_price":705.87}}'
        )
    url = (
        "https://www.pichau.com.br/fonte-corsair-rm750e-750w-full-modular-"
        "atx-3-1-pcie-5-1-cybenetics-gold-preto-cp-9020295-br"
    )
    offer = PichauSpider().extract_offer(_text_response(url, html))
    assert offer.price > 0
    assert offer.metadata.get("timed_promotion") is False
    assert "promotion" not in offer.metadata
