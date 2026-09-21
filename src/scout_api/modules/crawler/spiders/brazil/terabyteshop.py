"""TerabyteShop BR — parse-only adapter with timed campaign countdown."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import quote_plus, urljoin

from scrapy.http import Response

from ...core.exceptions import MissingPriceError, ParseError, RequestError
from ...core.fingerprints import canonicalize_url
from ...models.product import ProductDetails, ProductOffer
from ...models.search import SearchCandidate
from ...utils.parsing import parse_money
from ...utils.product_attributes import (
    format_identity_variant,
    resolve_product_identity,
)
from ...utils.timed_promotion import terabyte_promotion_from_html
from ..base import BaseStoreSpider

Availability = Literal["available", "out_of_stock", "unavailable"]

_PRODUCT_ID_RE = re.compile(r"/produto/(\d+)", re.I)


class TerabyteShopSpider(BaseStoreSpider):
    name = "terabyteshop"
    store, country, currency = "terabyteshop", "BR", "BRL"
    supports_search = True
    allowed_domains = ["terabyteshop.com.br"]
    start_urls: list[str] = []

    def build_search_url(self, query: str) -> str:
        return f"https://www.terabyteshop.com.br/busca?str={quote_plus(query.strip())}"

    def parse_search_results(self, response: Response) -> list[SearchCandidate]:
        candidates: list[SearchCandidate] = []
        seen: set[str] = set()
        for href in response.css(
            "a[href*='/produto/']::attr(href), .product-item a::attr(href)"
        ).getall():
            absolute = urljoin(response.url, (href or "").strip())
            if "/produto/" not in absolute:
                continue
            canonical = canonicalize_url(absolute)
            if canonical in seen:
                continue
            seen.add(canonical)
            match = _PRODUCT_ID_RE.search(canonical)
            candidates.append(
                SearchCandidate(
                    url=absolute,
                    product_id=match.group(1) if match else None,
                    metadata={"source": "terabyte-search"},
                )
            )
            if len(candidates) >= 10:
                break
        return candidates

    def extract_offer(self, response: Response) -> ProductOffer:
        self._ensure_product_page(response)
        json_ld = self.json_ld(response)
        offer_ld = self._offers_object(json_ld)
        price = self._price(response, offer_ld)
        original = self._original_price(response, price)
        product_id = self._product_id(response, json_ld)
        availability, availability_source = self._availability(offer_ld, response)
        promo = terabyte_promotion_from_html(response.text or "", product_id=product_id)
        metadata: dict[str, Any] = {
            "source": {
                "price": "json-ld-or-dom",
                "availability": availability_source,
                "promotion": promo["source"] if promo else "absent",
            }
        }
        if promo:
            metadata["promotion"] = promo

        return ProductOffer(
            store=self.store,
            country=self.country,
            product_id=product_id,
            sku=self._string(json_ld.get("sku")) or product_id,
            seller="TerabyteShop",
            url=response.url,
            canonical_url=canonicalize_url(response.url),
            currency=self.currency,
            price=price,
            original_price=original,
            discount_percentage=self._discount(price, original),
            pix_price=None,
            available=availability == "available",
            availability=availability,
            metadata=metadata,
        )

    def extract_details(self, response: Response) -> ProductDetails:
        self._ensure_product_page(response)
        json_ld = self.json_ld(response)
        title = self._string(json_ld.get("name")) or self.first(
            response, ["h1::text", "title::text"]
        )
        if not title:
            raise ParseError("Título do produto não encontrado")
        product_id = self._product_id(response, json_ld)
        brand = None
        brand_raw = json_ld.get("brand")
        if isinstance(brand_raw, dict):
            brand = self._string(brand_raw.get("name"))
        elif isinstance(brand_raw, str):
            brand = brand_raw.strip() or None
        resolved = resolve_product_identity(
            specifications={},
            structured={"brand": brand},
            title=title,
        )
        return ProductDetails(
            product_id=product_id,
            sku=self._string(json_ld.get("sku")) or product_id,
            title=title,
            brand=brand or resolved.value("brand"),
            model=resolved.value("model"),
            variant=format_identity_variant(resolved),
            gtin=resolved.value("gtin"),
            specifications={},
            images=[],
            metadata={"source": {"title": "json-ld-or-dom"}},
        )

    def extract_images(self, response: Response) -> list[str]:
        return self.normalize_image_urls(
            self.json_ld(response).get("image"), base_url=response.url
        )

    def _ensure_product_page(self, response: Response) -> None:
        if "/produto/" not in (response.url or "").casefold():
            raise ParseError("URL não parece PDP TerabyteShop")
        text = (response.text or "").casefold()
        if "cloudflare" in text and "just a moment" in text:
            # Signal upstream block so fetch can keep resolving (Camoufox /
            # proxy FALLBACK). Never map challenge HTML to a product.
            raise RequestError(
                "TerabyteShop apresentou challenge Cloudflare",
                code="UPSTREAM_BLOCKED",
                url=response.url,
            )

    def _product_id(self, response: Response, json_ld: dict[str, Any]) -> str:
        for key in ("sku", "productID", "productId"):
            value = self._string(json_ld.get(key))
            if value and value.isdigit():
                return value
        match = _PRODUCT_ID_RE.search(response.url or "")
        if match:
            return match.group(1)
        raise ParseError("product_id TerabyteShop não encontrado")

    def _price(self, response: Response, offer_ld: dict[str, Any]) -> Decimal:
        raw = offer_ld.get("price")
        if raw is not None:
            try:
                value = Decimal(str(raw))
                if value > 0:
                    return value.quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError, TypeError):
                pass
            try:
                return parse_money(str(raw), self.currency)
            except MissingPriceError:
                pass
        # Inline JS product state: 'price': 549.99
        match = re.search(
            r"['\"]price['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)",
            response.text or "",
        )
        if match:
            return Decimal(match.group(1))
        raise ParseError("Preço TerabyteShop não encontrado")

    def _original_price(self, response: Response, price: Decimal) -> Decimal | None:
        text = response.text or ""
        # Struck / "De" prices vary; prefer larger nearby money if present.
        for match in re.finditer(
            r"(?:de|por)\s*:?\s*R\$\s*([0-9\.\,]+)", text, flags=re.I
        ):
            try:
                money = parse_money(match.group(1), self.currency)
            except MissingPriceError:
                continue
            if money > price:
                return money
        return None

    def _availability(
        self, offer_ld: dict[str, Any], response: Response
    ) -> tuple[Availability, str]:
        avail = str(offer_ld.get("availability") or "").casefold()
        if "outofstock" in avail:
            return "out_of_stock", "json-ld"
        if "instock" in avail:
            return "available", "json-ld"
        text = (response.text or "").casefold()
        if "indispon" in text and "adicionar" not in text:
            return "out_of_stock", "dom-heuristic"
        return "available", "assumed-with-price"

    def _offers_object(self, json_ld: dict[str, Any]) -> dict[str, Any]:
        offers = json_ld.get("offers")
        if isinstance(offers, list) and offers:
            first = offers[0]
            return first if isinstance(first, dict) else {}
        return offers if isinstance(offers, dict) else {}

    @staticmethod
    def _string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _discount(price: Decimal, original: Decimal | None) -> Decimal | None:
        if original is None or original <= 0 or price >= original:
            return None
        return ((original - price) / original * Decimal("100")).quantize(
            Decimal("0.01")
        )
