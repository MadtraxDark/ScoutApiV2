"""Shared Amazon parsing behavior (ASIN, URL, variants, images, blocking)."""

from decimal import Decimal
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.core.proxy_policy import resolve_store_config
from scout_api.modules.crawler.services.store_resolver import resolve_store_spider
from scout_api.modules.crawler.spiders.amazon.parsing import (
    canonical_amazon_url,
    extract_asin,
    extract_color_images,
    extract_selected_variant_dimensions,
)
from scout_api.modules.crawler.spiders.brazil.amazon import AmazonBrazilSpider
from scout_api.modules.crawler.spiders.usa.amazon import AmazonUSSpider

FIXTURES = Path(__file__).parents[1] / "fixtures" / "amazon"


def response_from_fixture(name: str, url: str) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_amazon_domains_resolve_to_regional_spiders_with_shared_store_key() -> None:
    us = resolve_store_spider("https://www.amazon.com/dp/B09WNK39JN")
    br = resolve_store_spider("https://www.amazon.com.br/dp/B09WNK39JN")
    assert isinstance(us, AmazonUSSpider)
    assert isinstance(br, AmazonBrazilSpider)
    assert us.store == br.store == "amazon"
    assert us.country == "US" and us.currency == "USD"
    assert br.country == "BR" and br.currency == "BRL"

    us_cfg = resolve_store_config("https://www.amazon.com/dp/B09WNK39JN")
    br_cfg = resolve_store_config("https://www.amazon.com.br/dp/B09WNK39JN")
    assert us_cfg is not None and br_cfg is not None
    assert us_cfg.key == br_cfg.key == "amazon"
    assert us_cfg.country == "US" and br_cfg.country == "BR"
    # amazon.com must not swallow amazon.com.br
    assert us_cfg.domains == ("amazon.com",)
    assert br_cfg.domains == ("amazon.com.br",)


def test_asin_and_canonical_url_helpers() -> None:
    response = response_from_fixture(
        "us_available_amazon_sold.html",
        "https://www.amazon.com/Sony-something/dp/B09WNK39JN?psc=1",
    )
    assert extract_asin(response) == "B09WNK39JN"
    assert (
        canonical_amazon_url("amazon.com", "B09WNK39JN")
        == "https://www.amazon.com/dp/B09WNK39JN"
    )


def test_canonical_url_strips_tracking_and_slug_for_regression_asins() -> None:
    """URLs reais de busca/tracking não entram na identidade do produto."""
    assert (
        canonical_amazon_url("amazon.com.br", "B0GVTB7BGQ")
        == "https://www.amazon.com.br/dp/B0GVTB7BGQ"
    )
    assert (
        canonical_amazon_url("amazon.com", "B09V9Z1WLN")
        == "https://www.amazon.com/dp/B09V9Z1WLN"
    )
    tracking_br = (
        "https://www.amazon.com.br/Celular-Samsung/dp/B0GVTB7BGQ"
        "?ref_=Oct_d_obs&pd_rd_w=OJMdl&th=1&pf_rd_r=ABC"
    )
    tracking_us = (
        "https://www.amazon.com/SAMSUNG-Galaxy/dp/B09V9Z1WLN/ref=sr_1_2_sspa"
        "?keywords=smartphone&th=1"
    )
    assert resolve_store_spider(tracking_br).store == "amazon"
    assert resolve_store_spider(tracking_br).country == "BR"
    assert resolve_store_spider(tracking_us).country == "US"
    # Identidade canônica Amazon é host + /dp/ASIN (não o path com slug/query).
    assert canonical_amazon_url("amazon.com.br", "B0GVTB7BGQ") not in tracking_br
    assert "pd_rd_w" not in canonical_amazon_url("amazon.com.br", "B0GVTB7BGQ")
    assert "keywords" not in canonical_amazon_url("amazon.com", "B09V9Z1WLN")


def test_variant_dimensions_follow_twister_order() -> None:
    html = (FIXTURES / "us_available_amazon_sold.html").read_text(encoding="utf-8")
    dims = extract_selected_variant_dimensions(html, "B09WNK39JN")
    assert dims == {"color": "Charcoal", "configuration": "Device only"}


def test_color_images_prefer_hires() -> None:
    html = (FIXTURES / "us_available_amazon_sold.html").read_text(encoding="utf-8")
    images = extract_color_images(html)
    assert images[0].endswith("_SL1000_.jpg")
    assert "transparent-pixel" not in "".join(images)


def test_robot_challenge_raises_upstream_blocked_not_unavailable() -> None:
    response = response_from_fixture(
        "challenge_robot.html",
        "https://www.amazon.com/dp/B09WNK39JN",
    )
    with pytest.raises(RequestError) as exc:
        AmazonUSSpider().extract_offer(response)
    assert exc.value.code == "UPSTREAM_BLOCKED"


def test_out_of_stock_with_price_is_not_available() -> None:
    offer = AmazonUSSpider().extract_offer(
        response_from_fixture(
            "us_out_of_stock.html",
            "https://www.amazon.com/dp/B0D1XD1ZV3",
        )
    )
    assert offer.price == Decimal("199.00")
    assert offer.available is False
    assert offer.availability == "out_of_stock"
    assert offer.metadata.get("parent_asin") == "B0FBXVLLQF"
