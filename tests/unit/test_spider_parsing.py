from decimal import Decimal
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import ParseError
from scout_api.modules.crawler.spiders.base import BaseStoreSpider
from scout_api.modules.crawler.spiders.brazil.magazineluiza import MagazineLuizaSpider


class ExampleSpider(BaseStoreSpider):
    name = "example"
    store, country, currency = "example", "BR", "BRL"


def test_json_ld_product_is_normalized() -> None:
    body = (
        b'<h1>GPU Example</h1><script type="application/ld+json">'
        b'{"@type":"Product","name":"GPU Example","sku":"GPU-1",'
        b'"offers":{"price":"R$ 4.999,90","availability":"InStock"}}'
        b"</script>"
    )
    response = HtmlResponse(
        "https://example.test/gpu?utm_source=x",
        body=body,
        encoding="utf-8",
        request=Request("https://example.test/gpu"),
    )
    item = ExampleSpider().parse_product(response)
    assert item.title == "GPU Example"
    assert str(item.price) == "4999.90"
    assert item.currency == "BRL"
    assert item.sku == "GPU-1"


FIXTURES = Path(__file__).parents[1] / "fixtures" / "magazineluiza"


def response_from_fixture(name: str) -> HtmlResponse:
    url = (
        "https://www.magazineluiza.com.br/p/240590700/ga/gap5/?seller_id=magazineluiza"
    )
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_magalu_available_product() -> None:
    item = MagazineLuizaSpider().parse_product(
        response_from_fixture("product_available.html")
    )
    assert item.product_id == "240590700"
    assert item.currency == "BRL"
    assert item.price == Decimal("4399.00")
    assert item.pix_price == Decimal("4399.00")
    assert item.available is True
    assert item.availability == "available"
    assert item.seller == "magazineluiza"


def test_magalu_pix_and_original_prices_are_distinct() -> None:
    item = MagazineLuizaSpider().parse_product(
        response_from_fixture("product_discount_pix.html")
    )
    assert item.price == Decimal("4599.00")
    assert item.pix_price == Decimal("4599.00")
    assert item.original_price == Decimal("4999.00")


def test_magalu_out_of_stock_is_not_parse_failure() -> None:
    item = MagazineLuizaSpider().parse_product(
        response_from_fixture("product_out_of_stock.html")
    )
    assert item.available is False
    assert item.availability == "out_of_stock"


def test_magalu_missing_price_is_parse_error() -> None:
    url = "https://www.magazineluiza.com.br/p/no-price"
    response = HtmlResponse(
        url,
        body=b"<h1>Produto sem preco</h1><button>Comprar agora</button>",
        encoding="utf-8",
        request=Request(url),
    )
    with pytest.raises(ParseError):
        MagazineLuizaSpider().parse_product(response)
