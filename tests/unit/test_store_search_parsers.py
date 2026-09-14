"""Unit tests for store SERP parsers (HTML fixtures, no network)."""

from __future__ import annotations

from scrapy.http import HtmlResponse

from scout_api.modules.crawler.spiders.brazil.amazon import AmazonBrazilSpider
from scout_api.modules.crawler.spiders.brazil.kabum import KabumSpider
from scout_api.modules.crawler.spiders.brazil.magazineluiza import MagazineLuizaSpider
from scout_api.modules.crawler.spiders.brazil.shopee import ShopeeSpider
from scout_api.modules.crawler.spiders.paraguay.nissei import NisseiSpider
from scout_api.modules.crawler.spiders.paraguay.shoppingchina import ShoppingChinaSpider
from scout_api.modules.crawler.spiders.registry import stores_supporting_search
from scout_api.modules.crawler.spiders.usa.amazon import AmazonUSSpider
from scout_api.modules.crawler.spiders.usa.bestbuy import BestBuySpider


def _response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(url=url, body=body.encode("utf-8"), encoding="utf-8")


def test_kabum_parse_search_results() -> None:
    html = """
    <html><body>
      <a class="productLink" href="/produto/123456/memoria-kingston">Kingston</a>
      <a href="/produto/123456/memoria-kingston">dup</a>
      <a href="/produto/999/outro">Outro</a>
    </body></html>
    """
    spider = KabumSpider()
    results = spider.parse_search_results(
        _response("https://www.kabum.com.br/busca/kingston", html)
    )
    assert len(results) == 2
    assert results[0].product_id == "123456"
    assert "kabum.com.br/produto/" in results[0].url


def test_magalu_parse_search_results() -> None:
    html = """
    <html><body>
      <a data-testid="product-card-link" href="/iphone/p/jjhd6g4f9d/">iPhone</a>
      <a href="/busca/iphone/">ignore</a>
    </body></html>
    """
    spider = MagazineLuizaSpider()
    results = spider.parse_search_results(
        _response("https://www.magazineluiza.com.br/busca/iphone/", html)
    )
    assert len(results) == 1
    assert results[0].product_id == "jjhd6g4f9d"


def test_amazon_br_parse_search_results() -> None:
    html = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B0TESTASIN">
        <h2><a href="/dp/B0TESTASIN"><span>Produto Amazon</span></a></h2>
      </div>
      <div data-component-type="s-search-result" data-asin="">
        <h2><a href="/s?k=x"><span>Sponsored</span></a></h2>
      </div>
    </body></html>
    """
    spider = AmazonBrazilSpider()
    results = spider.parse_search_results(
        _response("https://www.amazon.com.br/s?k=teste", html)
    )
    assert len(results) == 1
    assert results[0].product_id == "B0TESTASIN"
    assert results[0].title == "Produto Amazon"


def test_amazon_us_parse_search_results() -> None:
    html = """
    <html><body>
      <div data-component-type="s-search-result" data-asin="B0USASIN01">
        <h2><a href="/dp/B0USASIN01"><span>US Product</span></a></h2>
      </div>
    </body></html>
    """
    spider = AmazonUSSpider()
    results = spider.parse_search_results(
        _response("https://www.amazon.com/s?k=teste", html)
    )
    assert len(results) == 1
    assert results[0].product_id == "B0USASIN01"
    assert results[0].metadata.get("source") == "amazon-us-search"


def test_bestbuy_parse_search_results() -> None:
    html = """
    <html><body>
      <a href="/product/sony-headphones/JJ123456">Sony</a>
      <a href="/site/sony-wh/6556754.p?skuId=6556754">Legacy</a>
      <a href="/site/searchpage.jsp?st=sony">ignore</a>
    </body></html>
    """
    spider = BestBuySpider()
    results = spider.parse_search_results(
        _response("https://www.bestbuy.com/site/searchpage.jsp?st=sony", html)
    )
    assert len(results) == 2
    assert results[0].product_id == "JJ123456"
    assert results[1].product_id == "6556754"


def test_nissei_parse_search_results() -> None:
    html = """
    <html><body>
      <a class="product-item-link" href="/py/apple-iphone-17-a3258-dual">iPhone</a>
      <a href="/py/catalogsearch/result/?q=iphone">ignore</a>
    </body></html>
    """
    spider = NisseiSpider()
    results = spider.parse_search_results(
        _response("https://nissei.com/py/catalogsearch/result/?q=iphone", html)
    )
    assert len(results) == 1
    assert results[0].url.endswith("/py/apple-iphone-17-a3258-dual")


def test_shoppingchina_parse_search_results() -> None:
    html = """
    <html><body>
      <a href="/producto/notebook-asus-12345/">Notebook</a>
      <a href="/produto/fone-999/">Fone</a>
      <a href="/site/search?query=x">ignore</a>
    </body></html>
    """
    spider = ShoppingChinaSpider()
    results = spider.parse_search_results(
        _response(
            "https://www.shoppingchina.com.py/site/search?query=note",
            html,
        )
    )
    assert len(results) == 2
    assert results[0].product_id == "12345"
    assert results[1].product_id == "999"


def test_shoppingchina_parse_quick_search_json() -> None:
    payload = """
    [
      {
        "title_po": "iPhone 17 256GB Preto",
        "url_po": "https://www.shoppingchina.com.py/produto/celular-apple-iphone-17-256gb-preto-1012345",
        "url_es": "https://www.shoppingchina.com.py/producto/celular-apple-iphone-17-256gb-preto-1012345"
      }
    ]
    """
    spider = ShoppingChinaSpider()
    results = spider.parse_search_results(
        _response(
            "https://www.shoppingchina.com.py/quick_search?search=iphone",
            payload,
        )
    )
    assert len(results) == 1
    assert results[0].product_id == "1012345"
    assert results[0].title == "iPhone 17 256GB Preto"
    assert results[0].metadata.get("source") == "shoppingchina-quick-search"


def test_shopee_parse_search_results() -> None:
    html = """
    <html><body>
      <a data-sqe="link" href="/Memoria-Kingston-i.341936748.29277977480">RAM</a>
      <a href="/search?keyword=x">ignore</a>
    </body></html>
    """
    spider = ShopeeSpider()
    results = spider.parse_search_results(
        _response("https://shopee.com.br/search?keyword=kingston", html)
    )
    assert len(results) == 1
    assert results[0].product_id == "29277977480"
    assert results[0].metadata.get("shop_id") == "341936748"


def test_shopee_parse_search_api_payload() -> None:
    html = """
    <html><body>
      <script type="application/json" data-shopee-search="1">
        {"items":[{"item_basic":{"itemid":999,"shopid":111,"name":"iPhone 17"}}]}
      </script>
    </body></html>
    """
    spider = ShopeeSpider()
    results = spider.parse_search_results(
        _response("https://shopee.com.br/search?keyword=iphone", html)
    )
    assert len(results) == 1
    assert results[0].product_id == "999"
    assert "product/111/999" in results[0].url
    assert results[0].metadata.get("source") == "shopee-search-api"


def test_shopee_parse_search_embedded_fallback() -> None:
    html = '<html><body><script>const x="i.111.222";</script></body></html>'
    spider = ShopeeSpider()
    results = spider.parse_search_results(
        _response("https://shopee.com.br/search?keyword=x", html)
    )
    assert len(results) == 1
    assert results[0].product_id == "222"
    assert "product/111/222" in results[0].url


def test_build_search_urls() -> None:
    assert "busca/" in KabumSpider().build_search_url("rtx 4060")
    assert "busca/" in MagazineLuizaSpider().build_search_url("rtx 4060")
    assert "s?k=" in AmazonBrazilSpider().build_search_url("rtx 4060")
    assert "amazon.com/s?k=" in AmazonUSSpider().build_search_url("rtx 4060")
    assert "searchpage.jsp" in BestBuySpider().build_search_url("rtx 4060")
    assert "nissei.com/py/catalogsearch/result" in NisseiSpider().build_search_url(
        "rtx 4060"
    )
    assert "quick_search?search=" in ShoppingChinaSpider().build_search_url("rtx 4060")
    assert "search?keyword=" in ShopeeSpider().build_search_url("rtx 4060")


def test_all_implemented_stores_support_search() -> None:
    supported = set(stores_supporting_search())
    expected = {
        "amazon_br",
        "amazon_us",
        "kabum",
        "magazineluiza",
        "shopee",
        "bestbuy",
        "nissei",
        "shoppingchina",
    }
    assert expected <= supported
