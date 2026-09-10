import re
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

from scrapy.http import Response

from ...core.exceptions import ParseError
from ...core.fingerprints import canonicalize_url
from ...models.product import ProductPriceItem
from ...utils.parsing import parse_money
from ..base import BaseStoreSpider


class MagazineLuizaSpider(BaseStoreSpider):
    """Parse a single Magazine Luiza product offer."""

    name = "magazineluiza"
    store, country, currency = "magazineluiza", "BR", "BRL"
    allowed_domains = ["magazineluiza.com.br", "m.magazineluiza.com.br"]
    start_urls: list[str] = []

    def parse_product(self, response: Response) -> ProductPriceItem:
        data = self.json_ld(response)
        offers = data.get("offers") if isinstance(data, dict) else None
        offer = offers if isinstance(offers, dict) else {}
        page_text = " ".join(response.css("body ::text").getall())

        title = data.get("name") or self.first(response, ["h1::text", "title::text"])
        if not title:
            raise ParseError("Título do produto não encontrado")

        price = self._price(response, offer, page_text)
        pix_price = self._pix_price(response, page_text)
        original_price = self._original_price(response, page_text)
        availability = self._availability(response, offer, page_text)
        product_id = (
            data.get("sku")
            or self.first(response, ["[itemprop='sku']::attr(content)"])
            or self._product_id(response.url)
        )
        if not product_id:
            raise ParseError("Identificador do produto não encontrado")

        seller = self._seller(response.url, page_text)
        return ProductPriceItem(
            store=self.store,
            country=self.country,
            product_id=str(product_id),
            sku=str(product_id),
            title=str(title).strip(),
            seller=seller,
            url=response.url,
            canonical_url=canonicalize_url(response.url),
            currency=self.currency,
            price=price,
            original_price=original_price,
            pix_price=pix_price,
            available=availability == "available",
            availability=availability,
            metadata={
                "source": {
                    "title": "json-ld-or-h1",
                    "price": "json-ld-or-price-label",
                    "pix_price": "pix-label",
                    "availability": "json-ld-or-purchase-signals",
                }
            },
        )

    def _price(
        self, response: Response, offer: dict[str, Any], page_text: str
    ) -> Decimal:
        raw = offer.get("price")
        if raw is not None and (
            isinstance(raw, int | float) or re.fullmatch(r"\d+(?:\.\d+)?", str(raw))
        ):
            return Decimal(str(raw))
        if raw is None:
            match = re.search(r"Preço\s+R\$\s*([\d.]+(?:,\d{2})?)", page_text, re.I)
            raw = match.group(1) if match else None
        return parse_money(str(raw) if raw is not None else None, self.currency)

    def _pix_price(self, response: Response, page_text: str) -> Decimal | None:
        del response
        raw = None
        match = re.search(r"R\$\s*([\d.]+(?:,\d{2})?)\s*no\s+Pix", page_text, re.I)
        if match:
            raw = match.group(1)
        return parse_money(raw, self.currency) if raw else None

    def _original_price(self, response: Response, page_text: str) -> Decimal | None:
        match = re.search(
            r"(?:De|Preço\s+original)\s*:?[\sR$]*([\d.]+(?:,\d{2})?)",
            page_text,
            re.I,
        )
        return parse_money(match.group(1), self.currency) if match else None

    @staticmethod
    def _availability(
        response: Response,
        offer: dict[str, Any],
        page_text: str,
    ) -> Literal["available", "out_of_stock", "unavailable"]:
        structured = str(offer.get("availability", "")).lower()
        if any(marker in structured for marker in ("outofstock", "soldout")):
            return "out_of_stock"
        if any(marker in structured for marker in ("discontinued", "unavailable")):
            return "unavailable"
        lower_text = page_text.lower()
        if re.search(
            r"produto\s+(?:esgotado|indisponível)|fora\s+de\s+estoque",
            lower_text,
        ):
            return "out_of_stock"
        if "indisponível" in lower_text or "indisponivel" in lower_text:
            return "unavailable"
        purchase_buttons = response.xpath(
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÀÃÂ', "
            "'abcdefghijklmnopqrstuvwxyzáàãâ'), 'adicionar à sacola') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÀÃÂ', "
            "'abcdefghijklmnopqrstuvwxyzáàãâ'), 'comprar agora')]"
        )
        if purchase_buttons:
            return "available"
        if any(
            signal in lower_text for signal in ("adicionar à sacola", "comprar agora")
        ):
            return "available"
        raise ParseError("Sinal de disponibilidade não encontrado")

    @staticmethod
    def _product_id(url: str) -> str | None:
        match = re.search(r"/p/([^/?]+)", urlparse(url).path)
        return match.group(1) if match else None

    @staticmethod
    def _seller(url: str, page_text: str) -> str | None:
        query_seller = parse_qs(urlparse(url).query).get("seller_id", [None])[0]
        if query_seller:
            return query_seller
        if re.search(r"Vendido\s+e\s+entregue\s+por\s+Magalu", page_text, re.I):
            return "magazineluiza"
        return None
