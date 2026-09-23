from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from scrapy.http import HtmlResponse, Request

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.services.store_resolver import resolve_store_spider
from scout_api.modules.crawler.spiders.brazil.pichau import PichauSpider
from scout_api.modules.crawler.utils.parsing import parse_money
from scout_api.modules.matching.search_adapters.brazil.pichau import PichauSearchAdapter

FIXTURES = Path(__file__).parents[1] / "fixtures" / "pichau"
PSU_URL = (
    "https://www.pichau.com.br/fonte-corsair-rm750e-750w-full-modular-"
    "atx-3-1-pcie-5-1-cybenetics-gold-preto-cp-9020295-br"
)
CPU_URL = (
    "https://www.pichau.com.br/processador-amd-ryzen-7-5800x3d-8-core-16-threads-"
    "3-4ghz-4-5ghz-turbo-cache-100mb-am4-100-100000651pof"
)


def response_from_fixture(name: str, url: str = PSU_URL) -> HtmlResponse:
    return HtmlResponse(
        url,
        body=(FIXTURES / name).read_bytes(),
        encoding="utf-8",
        request=Request(url),
    )


def test_pichau_domain_resolves_to_spider() -> None:
    spider = resolve_store_spider(PSU_URL)
    assert isinstance(spider, PichauSpider)
    assert spider.store == "pichau"
    assert spider.currency == "BRL"


def test_pichau_offer_prices_identity_and_installments() -> None:
    offer = PichauSpider().extract_offer(
        response_from_fixture("product_available.html")
    )
    assert offer.product_id == "54920"
    assert offer.sku == "CP-9020295-BR"
    assert offer.seller == "Pichau"
    assert offer.currency == "BRL"
    assert offer.price == Decimal("705.87")
    assert offer.pix_price == Decimal("599.99")
    assert offer.original_price == Decimal("941.16")
    assert offer.discount_percentage == Decimal("25.00")
    assert offer.installment_count == 12
    assert offer.installment_price == Decimal("58.82")
    assert offer.available is True
    assert offer.metadata["source"]["price"] == "pichau_prices.final_price"
    assert offer.metadata["source"]["pix_price"] == "pichau_prices.avista"
    assert offer.metadata["parse_quality"] == "rsc-complete"
    assert offer.metadata["timed_promotion"] is False
    assert "promotion" not in offer.metadata


def test_pichau_details_brand_specs_and_gtin() -> None:
    details = PichauSpider().extract_details(
        response_from_fixture("product_available.html")
    )
    assert "Corsair" in (details.title or "")
    assert details.brand == "Corsair"
    assert details.product_id == "54920"
    assert details.sku == "CP-9020295-BR"
    assert details.gtin == "0840006691068"
    assert details.specifications
    assert details.specifications.get("mpn") == "CP-9020295-BR"
    assert details.specifications.get("Potência") == "750"
    assert details.metadata["source"]["brand"] in {"rsc-marcas_info", "structured-data"}
    assert details.metadata["source"]["specifications"] == "rsc-attributes"


def test_pichau_cpu_identity_preserves_x3d_suffix() -> None:
    details = PichauSpider().extract_details(
        response_from_fixture("product_cpu_identity.html", CPU_URL)
    )
    offer = PichauSpider().extract_offer(
        response_from_fixture("product_cpu_identity.html", CPU_URL)
    )
    assert details.brand == "AMD"
    assert details.model is not None
    model_norm = details.model.upper().replace(" ", "")
    assert "5800X3D" in model_norm
    assert "X3D" in model_norm
    assert details.sku == "100-100000651POF"
    assert details.specifications.get("mpn") == "100-100000651POF"
    assert details.specifications.get("Socket") == "AM4"
    assert offer.price == Decimal("2517.64")
    assert offer.pix_price == Decimal("2299.00")
    assert offer.original_price == Decimal("2899.00")


def test_pichau_missing_original_stays_null() -> None:
    offer = PichauSpider().extract_offer(
        response_from_fixture("product_missing_original.html")
    )
    assert offer.price == Decimal("705.87")
    assert offer.pix_price == Decimal("599.99")
    assert offer.original_price is None


def test_pichau_missing_pix_stays_null() -> None:
    offer = PichauSpider().extract_offer(
        response_from_fixture("product_missing_pix.html")
    )
    assert offer.price == Decimal("705.87")
    assert offer.pix_price is None
    assert offer.original_price == Decimal("941.16")


def test_pichau_brazilian_money_format() -> None:
    assert parse_money("R$ 2.517,64", "BRL") == Decimal("2517.64")


def test_pichau_cloudflare_block_raises_upstream_blocked() -> None:
    with pytest.raises(RequestError) as exc:
        PichauSpider().extract_offer(response_from_fixture("block_cloudflare.html"))
    assert exc.value.code == "UPSTREAM_BLOCKED"


def test_pichau_malformed_page_raises_parse_error() -> None:
    with pytest.raises(ParseError):
        PichauSpider().extract_offer(response_from_fixture("malformed.html"))


def test_pichau_search_prefers_url_key_slugs() -> None:
    html = (
        "<!DOCTYPE html><html><body>"
        '<a href="/favorites">Fav</a>'
        '<script>self.__next_f.push([1,"'
        + json.dumps(
            json.dumps(
                {
                    "items": [
                        {
                            "url_key": (
                                "placa-mae-msi-b550-gaming-wifi6e-ddr4-"
                                "socket-amd-am4-atx-chipset-amd-b550"
                            )
                        }
                    ]
                }
            )
        )[1:-1]
        + '"])</script></body></html>'
    )
    response = HtmlResponse(
        "https://www.pichau.com.br/search?q=b550",
        body=html.encode("utf-8"),
        encoding="utf-8",
        request=Request("https://www.pichau.com.br/search?q=b550"),
    )
    candidates = PichauSearchAdapter().parse_candidates(response)
    assert candidates
    assert "favorites" not in candidates[0].url
    assert "placa-mae-msi-b550" in candidates[0].url


def test_pichau_404_raises_parse_error() -> None:
    html = (
        "<!DOCTYPE html><html><head>"
        "<title>404 - Página não encontrada! | Pichau</title>"
        "</head><body>nao encontrada</body></html>"
    )
    response = HtmlResponse(
        PSU_URL,
        body=html.encode("utf-8"),
        encoding="utf-8",
        status=404,
        request=Request(PSU_URL),
    )
    with pytest.raises(ParseError):
        PichauSpider().extract_offer(response)
