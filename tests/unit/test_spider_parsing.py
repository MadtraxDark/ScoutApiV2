# ruff: noqa: E501

from decimal import Decimal
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import ParseError
from scout_api.modules.crawler.spiders.base import BaseStoreSpider
from scout_api.modules.crawler.spiders.brazil.magazineluiza import MagazineLuizaSpider
from scout_api.modules.crawler.spiders.paraguay.nissei import NisseiSpider


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


def test_magalu_uses_offer_state_for_semantic_prices_and_identity() -> None:
    item = MagazineLuizaSpider().parse_product(
        response_from_fixture("product_structured_offer.html")
    )
    assert item.product_id == "aebh5a7a94"
    assert item.sku == "989702"
    assert item.brand == "Sony"
    assert item.model == "PS5 CFI 2114B Edição Digital"
    assert item.variant == "Branco"
    assert item.seller == "kabum"
    assert item.price == Decimal("5058.85")
    assert item.pix_price == Decimal("4805.91")
    assert item.original_price == Decimal("5288.85")
    assert item.discount_percentage == Decimal("5.00")
    assert item.installment_count == 10
    assert item.installment_price == Decimal("505.89")
    assert item.metadata["source"]["price"] == "product-offer-state"
    assert item.metadata["source"]["pix_price"] == "payment-method-pix"


def test_magalu_extract_offer_is_independent_of_catalog_details() -> None:
    spider = MagazineLuizaSpider()
    response = response_from_fixture("product_structured_offer.html")
    offer = spider.extract_offer(response)
    details = spider.extract_details(response)

    assert offer.price == Decimal("5058.85")
    assert offer.pix_price == Decimal("4805.91")
    assert offer.seller == "kabum"
    assert offer.available is True
    assert details.title
    assert details.brand == "Sony"
    assert details.model == "PS5 CFI 2114B Edição Digital"
    assert details.images == []
    assert "brand" not in offer.model_dump()
    assert "price" not in details.model_dump()


def test_magalu_extract_images_normalizes_gallery() -> None:
    spider = MagazineLuizaSpider()
    response = response_from_fixture("product_structured_offer.html")
    details = spider.extract_details(response)
    images = spider.extract_images(response)

    assert details.images == []
    assert images == [
        "https://a-static.mlcdn.com.br/ps5-front.jpg",
        "https://a-static.mlcdn.com.br/ps5-side.jpg",
        "https://www.magazineluiza.com.br/relative/ps5-back.jpg",
    ]


def test_magalu_does_not_infer_original_price_from_unrelated_numbers() -> None:
    url = "https://www.magazineluiza.com.br/p/no-old-price? seller_id=kabum"
    response = HtmlResponse(
        url,
        body=(
            b"<h1>Produto</h1><span>5% OFF em 10 parcelas</span>"
            b"<span>Preco R$ 480,00 no Pix</span><button>Comprar agora</button>"
        ),
        encoding="utf-8",
        request=Request(url),
    )
    item = MagazineLuizaSpider().parse_product(response)
    assert item.original_price is None


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


def test_nissei_extracts_structured_identity_and_rendered_installment() -> None:
    body = b"""
    <main id="maincontent">
      <title>Placa Madre Gigabyte X870 Aorus Stealth ICE AM5 DDR5 ATX</title>
      <div class="product-info-main">
        <h1><span class="base">Placa Madre Gigabyte X870 Aorus Stealth ICE AM5 DDR5 ATX</span></h1>
        <a class="amshopby-brand-title-link">GIGABYTE</a>
        <div class="price-box" data-role="priceBox" data-product-id="1644544">
          <span class="price-wrapper" data-price-amount="3226999.996001"
                data-price-type="finalPrice">
            <span class="price">Gs. 3.227.000</span>
          </span>
          <meta itemprop="price" content="3226999.996001">
        </div>
        <div class="stock available"><span>En stock</span></div>
        <div class="bancos-adheridos principal-cuotas">
          <h3>Hasta <span>18</span> cuotas
            <span>sin intereses de Gs. 179.278</span></h3>
        </div>
      </div>
      <table class="product-attribute-specs-table">
        <tr><th>UPC</th><td>889523051276</td></tr>
      </table>
      <form data-product-sku="148321"></form>
    </main>
    """
    url = "https://nissei.com/py/informatica/producto"
    response = HtmlResponse(url, body=body, encoding="utf-8", request=Request(url))

    item = NisseiSpider().parse_product(response)

    assert item.title == "Placa Madre Gigabyte X870 Aorus Stealth ICE AM5 DDR5 ATX"
    assert item.gtin == "889523051276"
    assert item.brand == "GIGABYTE"
    assert item.installment_price == Decimal("179278")
    assert item.installment_count == 18
    assert item.original_price is None
    assert item.discount_percentage is None
    assert item.model is None
    assert item.variant is None
    assert item.seller is None
    assert item.shipping_price is None
    assert item.available is True


def test_nissei_extract_images_deduplicates_magento_cache_variants() -> None:
    body = b"""
    <div class="product.media">
      <img src="/media/catalog/product/cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/2/n/main.jpg">
      <img src="/media/catalog/product/cache/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/2/n/main.jpg">
      <img src="/media/catalog/product/cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/A/Q/detail.jpg">
      <img src="/media/catalog/product/cache/cccccccccccccccccccccccccccccccc/A/Q/detail.jpg">
      <img src="/media/catalog/product/cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/T/7/side.jpg">
    </div>
    """
    url = "https://nissei.com/br/produto"
    response = HtmlResponse(url, body=body, encoding="utf-8", request=Request(url))

    images = NisseiSpider().extract_images(response)

    assert images == [
        "https://nissei.com/media/catalog/product/cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/2/n/main.jpg",
        "https://nissei.com/media/catalog/product/cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/A/Q/detail.jpg",
        "https://nissei.com/media/catalog/product/cache/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/T/7/side.jpg",
    ]
