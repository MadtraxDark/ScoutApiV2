import re
from decimal import Decimal
from typing import Any, Literal

from scrapy.http import Response

from ...core.exceptions import ParseError
from ...core.fingerprints import canonicalize_url
from ...models.product import ProductPriceItem
from ...utils.parsing import parse_money
from ..base import BaseStoreSpider

Availability = Literal["available", "out_of_stock", "unavailable"]


class NisseiSpider(BaseStoreSpider):
    """Parse a single Nissei (Paraguay) product offer."""

    name = "nissei"
    store, country, currency = "nissei", "PY", "PYG"
    allowed_domains = ["nissei.com"]
    start_urls: list[str] = []

    def parse_product(self, response: Response) -> ProductPriceItem:
        data = self.json_ld(response)
        offers = data.get("offers") if isinstance(data, dict) else None
        offer = offers if isinstance(offers, dict) else {}
        page_text = " ".join(response.css("body ::text").getall())

        title = data.get("name") or self.first(response, ["h1::text", "title::text"])
        if not title:
            raise ParseError("Título do produto não encontrado")

        raw_price = offer.get("price") or self.first(
            response,
            [
                "[itemprop='price']::attr(content)",
                "[data-price-amount]::attr(data-price-amount)",
                ".price::text",
                ".product-price::text",
            ],
        )
        price = self._price(raw_price)

        product_id = (
            data.get("sku")
            or self.first(
                response,
                [
                    "[itemprop='sku']::attr(content)",
                    "[itemprop='sku']::text",
                    "[data-product-id]::attr(data-product-id)",
                ],
            )
            or self._sku_from_text(page_text)
        )
        if not product_id:
            product_id = canonicalize_url(response.url)

        availability = self._availability(offer, page_text)
        return ProductPriceItem(
            store=self.store,
            country=self.country,
            product_id=str(product_id).strip(),
            sku=str(product_id).strip(),
            title=str(title).strip(),
            url=response.url,
            canonical_url=canonicalize_url(response.url),
            currency=self.currency,
            price=Decimal(price),
            available=availability == "available",
            availability=availability,
            metadata={
                "source": {"title": "json-ld-or-h1", "price": "json-ld-or-magento"}
            },
        )

    def _price(self, raw: object) -> Decimal:
        if raw is None:
            return parse_money(None, self.currency)
        text = str(raw).strip()
        # Magento often exposes a plain decimal with '.' as radix.
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return Decimal(text).quantize(Decimal("1"))
        return parse_money(text, self.currency)

    @staticmethod
    def _sku_from_text(page_text: str) -> str | None:
        match = re.search(r"SKU\s*[#:]?\s*(\d+)", page_text, re.I)
        return match.group(1) if match else None

    @staticmethod
    def _availability(offer: dict[str, Any], page_text: str) -> Availability:
        structured = str(offer.get("availability", "")).lower()
        if any(marker in structured for marker in ("outofstock", "soldout")):
            return "out_of_stock"
        lower = page_text.lower()
        if "agotado" in lower or "sin stock" in lower or "out of stock" in lower:
            return "out_of_stock"
        if "en stock" in lower or "in stock" in structured:
            return "available"
        if "instock" in structured:
            return "available"
        return "available"
