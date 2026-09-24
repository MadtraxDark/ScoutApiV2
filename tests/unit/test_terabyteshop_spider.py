"""TerabyteShop PDP spider — generic extraction regression tests."""

from __future__ import annotations

from decimal import Decimal

from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.spiders.brazil.terabyteshop import TerabyteShopSpider


def _response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(
        url, body=body.encode("utf-8"), encoding="utf-8", request=Request(url)
    )


_PDP_URL = (
    "https://www.terabyteshop.com.br/produto/99901/"
    "placa-exemplo-chipset-x-ddr5"
    "?gclid=tracking&gad_source=1"
)

# Synthetic PDP shaped like the live Terabyte storefront (label/value accordion,
# valVista/pix, installments, gallery /produto/g/, JSON-LD with brand-as-sku quirk).
_PDP_HTML = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
<title>Placa Exemplo Brand Modelline X DDR5 | Terabyte</title>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Placa Exemplo Brand Modelline X DDR5 | Terabyte",
  "image": "https://img.terabyteshop.com.br/produto/p/placa-exemplo_1.png",
  "sku": "Brand",
  "mpn": "Modellite X",
  "gtin13": "7891234567890",
  "brand": {"@type": "Brand", "name": "Brand"},
  "offers": {
    "@type": "Offer",
    "url": "https://www.terabyteshop.com.br/produto/99901/placa-exemplo",
    "priceCurrency": "BRL",
    "price": "999.99",
    "priceValidUntil": "2026-12-31",
    "availability": "http://schema.org/InStock"
  }
}
</script>
<script type="application/ld+json">
{"@type":"Organization","name":"Terabyte"}
</script>
</head>
<body>
<h1>Placa Exemplo Brand Modelline X DDR5</h1>
<p class="precode">De: <del>R$ 1.499,90</del> por:</p>
<p id="valVista" class="val-prod valVista">R$ 999,99</p>
<small>à vista com 15% de desconto no pix</small>
<span id="valParc" class="valParc">R$ 1.176,46</span>
<span id="nParc" class="laranja nParc">12x</span>
de <span id="Parc" class="Parc">R$ 98,04</span>
<span id="jrParc" class="inf_juros">sem juros no cartão</span>
<script>$('#ctd99901').countdown('2026/12/31 10:00:59');</script>
<div class="especificacoes">
  <div class="panel panel-default">
    <div class="panel-heading"><span>Especificações Técnicas</span></div>
    <div class="panel-body">
      <p><strong>Marca:</strong><br />Brand</p>
      <p><strong>Modelo:</strong><br />Modellite X</p>
      <p><strong>CPU:</strong><br />AMD Socket AM5, suporte para Ryzen</p>
      <p><strong>Chipset:</strong><br />AMD B650</p>
      <p><strong>Memória:</strong><br />4 x soquetes DIMM DDR5</p>
      <p><strong>Form Factor:</strong><br />mATX</p>
    </div>
  </div>
</div>
<img src="https://img.terabyteshop.com.br/produto/g/placa-exemplo_1.png" />
<img src="https://img.terabyteshop.com.br/produto/g/placa-exemplo_2.png" />
<img src="https://img.terabyteshop.com.br/produto/p/placa-exemplo_1.png" />
<img src="https://img.terabyteshop.com.br/terabyte-logo.svg" />
</body>
</html>
"""


def test_prepare_fetch_url_strips_tracking() -> None:
    spider = TerabyteShopSpider()
    prepared = spider.prepare_fetch_url(_PDP_URL)
    assert "gclid" not in prepared
    assert "gad_source" not in prepared
    assert "/produto/99901/" in prepared


def test_extract_offer_prices_and_promotion() -> None:
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(_PDP_URL, _PDP_HTML))
    assert offer.product_id == "99901"
    assert offer.sku == "99901"
    # Cross-store: price = cartão; pix_price = à vista/Pix; never swap.
    assert offer.price == Decimal("1176.46")
    assert offer.pix_price == Decimal("999.99")
    assert offer.original_price == Decimal("1499.90")
    assert offer.original_price != offer.price
    assert offer.pix_price != offer.price
    assert offer.installment_count == 12
    assert offer.installment_price == Decimal("98.04")
    # Promotional discount: original → sale (Pix/à vista), not payment markup.
    assert offer.discount_percentage == Decimal("33.33")
    assert offer.availability == "available"
    assert offer.canonical_url.endswith("/produto/99901/placa-exemplo-chipset-x-ddr5")
    assert "gclid" not in offer.canonical_url
    assert offer.metadata["promotion"]["source"] == "terabyte.jquery.countdown"
    assert offer.metadata["source"]["price"] == "dom-valParc"
    assert offer.metadata["source"]["pix_price"] == "dom-valVista-pix"


def test_original_price_kept_when_less_than_card() -> None:
    """Semantic \"De\" must survive even when original < card total."""
    html = _PDP_HTML.replace(
        '<p class="precode">De: <del>R$ 1.499,90</del> por:</p>',
        '<p class="precode">De: <del>R$ 1.099,90</del> por:</p>',
    )
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(_PDP_URL, html))
    assert offer.price == Decimal("1176.46")  # card
    assert offer.pix_price == Decimal("999.99")
    assert offer.original_price == Decimal("1099.90")
    assert offer.original_price < offer.price
    assert offer.pix_price < offer.original_price < offer.price
    assert offer.metadata["source"]["original_price"] == "dom-precode-del"
    warnings = (offer.metadata.get("pricing") or {}).get("consistency_warnings") or []
    assert "original_lt_card" in warnings


def test_original_price_kept_above_card() -> None:
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(_PDP_URL, _PDP_HTML))
    assert offer.original_price == Decimal("1499.90")
    assert offer.original_price > offer.price


def test_json_ld_avista_is_not_promoted_to_card_price() -> None:
    """Terabyte JSON-LD offers.price matches Pix/à vista — must not become price."""
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(_PDP_URL, _PDP_HTML))
    assert offer.price == Decimal("1176.46")
    assert offer.metadata["source"]["price"] != "json-ld"


def test_card_without_strikethrough_has_null_original() -> None:
    html = _PDP_HTML.replace(
        '<p class="precode">De: <del>R$ 1.499,90</del> por:</p>',
        "",
    )
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(_PDP_URL, html))
    assert offer.price == Decimal("1176.46")
    assert offer.pix_price == Decimal("999.99")
    assert offer.original_price is None
    assert offer.discount_percentage is None


def test_no_pix_label_leaves_pix_null() -> None:
    html = (
        _PDP_HTML.replace("à vista com 15% de desconto no pix", "preço promocional")
        .replace("à vista com 15% de desconto no pix", "preço promocional")
        .replace("no pix", "no cartão")
    )
    # Strip remaining pix mentions from fixture body copy only around valVista.
    html = html.replace("desconto no pix", "desconto").replace(" no pix", "")
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(_response(_PDP_URL, html))
    assert offer.price == Decimal("1176.46")
    # Without an explicit Pix/à-vista payment label, do not invent pix_price.
    assert offer.pix_price is None


def test_extract_details_specs_identity_and_gtin() -> None:
    spider = TerabyteShopSpider()
    details = spider.extract_details(_response(_PDP_URL, _PDP_HTML))
    assert details.product_id == "99901"
    assert details.sku == "99901"
    assert details.gtin == "7891234567890"
    assert details.brand == "Brand"
    assert "Modellite" in (details.model or "")
    assert "| Terabyte" not in details.title
    assert details.specifications.get("Marca") == "Brand"
    assert details.specifications.get("Modelo") == "Modellite X"
    assert "AM5" in details.specifications.get("CPU", "")
    assert details.specifications.get("Chipset") == "AMD B650"
    assert details.metadata["source"]["specifications"] == "html-accordion"


def test_extract_images_prefers_gallery() -> None:
    spider = TerabyteShopSpider()
    images = spider.extract_images(_response(_PDP_URL, _PDP_HTML))
    assert len(images) >= 2
    assert all("/produto/g/" in url for url in images)
    assert all("logo" not in url for url in images)


def test_challenge_html_is_upstream_blocked() -> None:
    html = (
        "<html><title>Just a moment...</title><body>cloudflare challenge</body></html>"
    )
    spider = TerabyteShopSpider()
    try:
        spider.extract_offer(
            _response("https://www.terabyteshop.com.br/produto/1/x", html)
        )
        raise AssertionError("expected RequestError")
    except RequestError as exc:
        assert exc.code == "UPSTREAM_BLOCKED"


def test_incomplete_pdp_raises_parse_error() -> None:
    html = "<html><head><title>Loja</title></head><body><h1>Home</h1></body></html>"
    spider = TerabyteShopSpider()
    try:
        spider.extract_offer(
            _response("https://www.terabyteshop.com.br/produto/1/x", html)
        )
        raise AssertionError("expected ParseError")
    except ParseError:
        pass


def test_json_ld_graph_finds_product_not_organization() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Organization","name":"Terabyte"}
    </script>
    <script type="application/ld+json">
    {"@type":"Product","name":"Item Y","sku":"Brand","mpn":"Y-1",
     "gtin13":"123","brand":{"name":"Brand"},
     "offers":{"price":"50.00","availability":"http://schema.org/InStock"}}
    </script>
    </head>
    <body>
    <h1>Item Y</h1>
    <p id="valVista">R$ 50,00</p>
    <div class="especificacoes"><p><strong>Modelo:</strong><br />Y-1</p></div>
    </body></html>
    """
    spider = TerabyteShopSpider()
    offer = spider.extract_offer(
        _response("https://www.terabyteshop.com.br/produto/55/item-y", html)
    )
    details = spider.extract_details(
        _response("https://www.terabyteshop.com.br/produto/55/item-y", html)
    )
    # Only à-vista published → last-resort price; no inventing a card total.
    assert offer.price == Decimal("50.00")
    assert details.title.startswith("Item Y")
    assert details.model is not None
