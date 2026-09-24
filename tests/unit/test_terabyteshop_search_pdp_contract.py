"""Contract: TerabyteShop SearchAdapter candidates → PDP spider parse."""

from __future__ import annotations

from decimal import Decimal

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.spiders.brazil.terabyteshop import TerabyteShopSpider
from scout_api.modules.matching.search_adapters.brazil.terabyteshop import (
    TerabyteShopSearchAdapter,
)


def _response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(
        url, body=body.encode("utf-8"), encoding="utf-8", request=Request(url)
    )


def test_search_candidate_url_parses_as_pdp() -> None:
    serp = """
    <html><body>
      <a href="/produto/777/item-a">A</a>
      <a href="/produto/888/item-b?gclid=x">B</a>
    </body></html>
    """
    adapter = TerabyteShopSearchAdapter()
    candidates = adapter.parse_candidates(
        _response("https://www.terabyteshop.com.br/busca?str=placa", serp)
    )
    assert candidates
    candidate = candidates[0]
    assert candidate.product_id == "777"

    pdp = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Item A","sku":"Brand","mpn":"Item-A",
      "brand":{"name":"Brand"},"gtin13":"12345678",
      "offers":{"price":"10.00","availability":"http://schema.org/InStock"}}
    </script>
    </head><body>
    <h1>Item A</h1>
    <p id="valVista">R$ 10,00</p>
    <div class="especificacoes">
      <p><strong>Modelo:</strong><br />Item-A</p>
      <p><strong>Marca:</strong><br />Brand</p>
    </div>
    </body></html>
    """
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(candidate.url, pdp))
    details = spider.extract_details(_response(candidate.url, pdp))
    assert offer.product_id == "777"
    assert offer.price == Decimal("10.00")
    assert details.title.startswith("Item A")
    assert details.specifications.get("Modelo") == "Item-A"
