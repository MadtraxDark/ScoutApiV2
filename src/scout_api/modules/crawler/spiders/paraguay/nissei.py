import re
from decimal import Decimal
from typing import Any, Literal

from scrapy.http import Response

from ...core.exceptions import ParseError
from ...core.fingerprints import canonicalize_url
from ...models.product import ProductDetails, ProductOffer
from ...utils.parsing import parse_money
from ..base import BaseStoreSpider

Availability = Literal["available", "out_of_stock", "unavailable"]


class NisseiSpider(BaseStoreSpider):
    """Parse a single Nissei (Paraguay) product offer and catalog details."""

    name = "nissei"
    store, country, currency = "nissei", "PY", "PYG"
    allowed_domains = ["nissei.com"]
    start_urls: list[str] = []

    def extract_offer(self, response: Response) -> ProductOffer:
        data = self.json_ld(response)
        offers = data.get("offers") if isinstance(data, dict) else None
        offer = offers if isinstance(offers, dict) else {}
        page_text = " ".join(response.css("body ::text").getall())
        product_root = response.css(".product-info-main")

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
        original_price = self._original_price(product_root)
        discount_percentage = self._discount_percentage(price, original_price)
        installment_price, installment_count = self._installment(product_root)

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
        return ProductOffer(
            store=self.store,
            country=self.country,
            product_id=str(product_id).strip(),
            sku=str(product_id).strip(),
            url=response.url,
            canonical_url=canonicalize_url(response.url),
            currency=self.currency,
            price=Decimal(price),
            original_price=original_price,
            discount_percentage=discount_percentage,
            installment_price=installment_price,
            installment_count=installment_count,
            available=availability == "available",
            availability=availability,
            metadata={"source": {"price": "json-ld-or-magento"}},
        )

    def extract_details(self, response: Response) -> ProductDetails:
        data = self.json_ld(response)
        page_text = " ".join(response.css("body ::text").getall())
        product_root = response.css(".product-info-main")

        title = data.get("name") or self.first(
            response, ["h1 .base::text", "h1::text", "title::text"]
        )
        if not title:
            raise ParseError("Título do produto não encontrado")

        brand = self.first(product_root, [".amshopby-brand-title-link::text"])
        gtin = self._attribute_value(response, "UPC")
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

        return ProductDetails(
            product_id=str(product_id).strip(),
            sku=str(product_id).strip(),
            gtin=gtin,
            title=str(title).strip(),
            brand=brand,
            metadata={"source": {"title": "json-ld-or-h1"}},
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
    def _attribute_value(response: Response, label: str) -> str | None:
        """Read a product specification by its explicit table label."""
        for row in response.css(".product-attribute-specs-table tr"):
            key = " ".join(row.css("th::text").getall()).strip()
            if key.casefold() == label.casefold():
                value = " ".join(row.css("td::text").getall()).strip()
                return value or None
        return None

    @staticmethod
    def _original_price(product_root: Any) -> Decimal | None:
        raw = product_root.css(
            ".price-box[data-role='priceBox'] "
            ".price-wrapper[data-price-type='oldPrice']::attr(data-price-amount)"
        ).get()
        if not raw:
            return None
        return Decimal(raw).quantize(Decimal("1"))

    @staticmethod
    def _discount_percentage(
        price: Decimal, original_price: Decimal | None
    ) -> Decimal | None:
        if original_price is None or original_price <= price:
            return None
        return ((original_price - price) * 100 / original_price).quantize(
            Decimal("0.01")
        )

    @staticmethod
    def _installment(product_root: Any) -> tuple[Decimal | None, int | None]:
        """Use the installment amount/count explicitly rendered by Nissei's page JS."""
        text = " ".join(
            product_root.css(
                ".principal-cuotas h3::text, .principal-cuotas h3 *::text"
            ).getall()
        )
        match = re.search(
            r"Hasta\s+(\d+)\s+cuotas.*?Gs\.\s*([\d.]+)", text, re.I | re.S
        )
        if not match:
            return None, None
        amount = parse_money(match.group(2), "PYG")
        return Decimal(amount), int(match.group(1))

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
