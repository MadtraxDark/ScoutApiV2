"""Pichau BR — Next.js RSC product payload (no timed promo timer observed)."""

from __future__ import annotations

import json
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
from ..base import BaseStoreSpider

Availability = Literal["available", "out_of_stock", "unavailable"]

# Magento/Next product blob embedded in RSC flight data.
_PRODUCT_BLOB_RE = re.compile(
    r'"product"\s*:\s*(\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\})',
    re.S,
)


class PichauSpider(BaseStoreSpider):
    name = "pichau"
    store, country, currency = "pichau", "BR", "BRL"
    supports_search = True
    allowed_domains = ["pichau.com.br"]
    start_urls: list[str] = []

    def build_search_url(self, query: str) -> str:
        return f"https://www.pichau.com.br/search?q={quote_plus(query.strip())}"

    def parse_search_results(self, response: Response) -> list[SearchCandidate]:
        candidates: list[SearchCandidate] = []
        seen: set[str] = set()
        for href in response.css("a[href]::attr(href)").getall():
            absolute = urljoin(response.url, (href or "").strip())
            path = absolute.split("?", 1)[0]
            if "pichau.com.br" not in path:
                continue
            # Product pages are slug paths without /search
            if "/search" in path or path.rstrip("/").endswith("pichau.com.br"):
                continue
            if path.count("/") < 3:
                continue
            canonical = canonicalize_url(absolute)
            if canonical in seen:
                continue
            # Prefer slugs that look like products (contain sku-ish tokens)
            if not re.search(r"[a-z0-9-]{8,}", path.split("/")[-1]):
                continue
            seen.add(canonical)
            candidates.append(
                SearchCandidate(
                    url=absolute,
                    metadata={"source": "pichau-search"},
                )
            )
            if len(candidates) >= 10:
                break
        return candidates

    def extract_offer(self, response: Response) -> ProductOffer:
        self._ensure_product_page(response)
        product = self._product_blob(response)
        json_ld = self.json_ld(response)
        offer_ld = self._offers_object(json_ld)

        prices = product.get("pichau_prices")
        prices = prices if isinstance(prices, dict) else {}
        avista = self._money(prices.get("avista"))
        final_price = self._money(
            prices.get("final_price") or product.get("special_price")
        )
        base_price = self._money(prices.get("base_price"))
        ld_price = self._money(offer_ld.get("price"))

        # Commercial price: prefer PIX/à vista when present; else card/final.
        if avista is not None:
            price, price_source = avista, "pichau_prices.avista"
            pix_price = avista
        elif final_price is not None:
            price, price_source = final_price, "pichau_prices.final_price"
            pix_price = None
        elif ld_price is not None:
            price, price_source = ld_price, "json-ld"
            pix_price = None
        else:
            raise ParseError("Preço Pichau não encontrado")

        original = None
        for candidate in (base_price, final_price, ld_price):
            if candidate is not None and candidate > price:
                original = candidate
                break

        sku = self._string(product.get("sku")) or self._sku_from_url(response.url)
        product_id = (
            self._string(product.get("id"))
            or sku
            or self._string(json_ld.get("sku"))
            or "unknown"
        )
        availability, availability_source = self._availability(
            product, offer_ld, response
        )

        # Research 2026-09-21: RSC has special_price / pichau_prices but NO
        # countdown / special_to_date / expires — do not invent a timer.
        metadata: dict[str, Any] = {
            "source": {
                "price": price_source,
                "availability": availability_source,
                "promotion": "absent-no-structured-expiry",
            },
            "pichau_prices": {
                key: prices.get(key)
                for key in (
                    "avista",
                    "avista_discount",
                    "avista_method",
                    "base_price",
                    "final_price",
                )
                if key in prices
            },
            "special_price": product.get("special_price"),
            "timed_promotion": False,
        }

        return ProductOffer(
            store=self.store,
            country=self.country,
            product_id=str(product_id),
            sku=sku,
            seller="Pichau",
            url=response.url,
            canonical_url=canonicalize_url(response.url),
            currency=self.currency,
            price=price,
            original_price=original,
            discount_percentage=self._discount(price, original),
            pix_price=pix_price,
            available=availability == "available",
            availability=availability,
            metadata=metadata,
        )

    def extract_details(self, response: Response) -> ProductDetails:
        self._ensure_product_page(response)
        product = self._product_blob(response)
        json_ld = self.json_ld(response)
        title = (
            self._string(product.get("name"))
            or self._string(json_ld.get("name"))
            or self.first(response, ["h1::text", "title::text"])
        )
        if not title:
            raise ParseError("Título do produto não encontrado")
        brand = None
        marcas = product.get("marcas_info")
        if isinstance(marcas, dict):
            brand = self._string(marcas.get("name"))
        sku = self._string(product.get("sku")) or self._sku_from_url(response.url)
        product_id = self._string(product.get("id")) or sku or "unknown"
        resolved = resolve_product_identity(
            specifications={},
            structured={"brand": brand},
            title=title,
        )
        return ProductDetails(
            product_id=str(product_id),
            sku=sku,
            title=title,
            brand=brand or resolved.value("brand"),
            model=resolved.value("model"),
            variant=format_identity_variant(resolved),
            gtin=resolved.value("gtin"),
            specifications={},
            images=[],
            metadata={"source": {"title": "rsc-or-jsonld"}},
        )

    def extract_images(self, response: Response) -> list[str]:
        return self.normalize_image_urls(
            self.json_ld(response).get("image"), base_url=response.url
        )

    def _ensure_product_page(self, response: Response) -> None:
        text = (response.text or "").casefold()
        if "just a moment" in text and "cloudflare" in text:
            # Keep resolution path open (Camoufox / proxy FALLBACK).
            raise RequestError(
                "Pichau apresentou challenge Cloudflare",
                code="UPSTREAM_BLOCKED",
                url=response.url,
            )
        if "site em manutenção" in text or "pru pru" in text:
            raise ParseError("Pichau em manutenção / HTML não-PDP")

    def _product_blob(self, response: Response) -> dict[str, Any]:
        text = response.text or ""
        # Prefer unescaped RSC product object.
        for match in _PRODUCT_BLOB_RE.finditer(text):
            raw = match.group(1)
            # Soft unescape common Next flight escapes when present.
            candidate = raw
            if "\\'" in candidate or '\\"' in candidate:
                candidate = (
                    candidate.replace('\\"', '"')
                    .replace("\\n", "\n")
                    .replace("\\/", "/")
                )
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and (
                value.get("sku") or value.get("pichau_prices") or value.get("id")
            ):
                return value

        # Fallback: reconstruct minimal fields from scattered tokens.
        sku_match = re.search(r'"sku"\s*:\s*"([^"]+)"', text)
        avista_match = re.search(r'"avista"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
        final_match = re.search(r'"final_price"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
        special_match = re.search(r'"special_price"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text)
        name_match = re.search(r'"name"\s*:\s*"(Fonte[^"]{5,120})"', text)
        if not (sku_match or avista_match or final_match or special_match):
            # JSON-LD only path
            return {}
        out: dict[str, Any] = {}
        if sku_match:
            out["sku"] = sku_match.group(1)
        if name_match:
            out["name"] = name_match.group(1)
        prices: dict[str, Any] = {}
        if avista_match:
            prices["avista"] = float(avista_match.group(1))
        if final_match:
            prices["final_price"] = float(final_match.group(1))
        if prices:
            out["pichau_prices"] = prices
        if special_match:
            out["special_price"] = float(special_match.group(1))
        return out

    def _availability(
        self,
        product: dict[str, Any],
        offer_ld: dict[str, Any],
        response: Response,
    ) -> tuple[Availability, str]:
        stock = product.get("stock_status") or product.get("quantity")
        if stock in (0, "0", False):
            return "out_of_stock", "rsc-stock"
        avail = str(offer_ld.get("availability") or "").casefold()
        if "outofstock" in avail:
            return "out_of_stock", "json-ld"
        if "instock" in avail:
            return "available", "json-ld"
        return "available", "assumed-with-price"

    def _offers_object(self, json_ld: dict[str, Any]) -> dict[str, Any]:
        offers = json_ld.get("offers")
        if isinstance(offers, list) and offers:
            first = offers[0]
            return first if isinstance(first, dict) else {}
        return offers if isinstance(offers, dict) else {}

    @staticmethod
    def _sku_from_url(url: str) -> str | None:
        # Many Pichau slugs end with manufacturer SKU.
        slug = url.rstrip("/").split("/")[-1]
        match = re.search(r"([A-Z]{1,5}-?\d{4,}[A-Z0-9\-]*)", slug, re.I)
        return match.group(1).upper() if match else None

    @staticmethod
    def _money(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            amount = Decimal(str(value))
            return amount.quantize(Decimal("0.01")) if amount > 0 else None
        except (InvalidOperation, ValueError, TypeError):
            pass
        try:
            return parse_money(str(value), "BRL")
        except MissingPriceError:
            return None

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
