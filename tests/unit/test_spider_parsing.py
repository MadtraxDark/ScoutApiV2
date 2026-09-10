from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.spiders.base import BaseStoreSpider


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
