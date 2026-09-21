"""Mercado Livre BR store adapter — parse-only (JSON-LD first)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from scrapy.http import Response

from ...core.exceptions import MissingPriceError, ParseError, RequestError
from ...core.fingerprints import canonicalize_url
from ...models.product import (
    ProductDetails,
    ProductOffer,
)
from ...models.search import SearchCandidate
from ...utils.parsing import parse_money
from ...utils.product_attributes import (
    format_identity_variant,
    resolve_product_identity,
)
from ..base import BaseStoreSpider

Availability = Literal["available", "out_of_stock", "unavailable"]

_CATALOG_ID_RE = re.compile(r"/p/(MLB\d+)(?:[/?]|$)", re.I)
_ITEM_ID_RE = re.compile(r"MLB-?(\d{8,})", re.I)
_ITEM_ID_FILTER_RE = re.compile(r"item_id[=:]?(MLB\d+)", re.I)


class MercadoLivreSpider(BaseStoreSpider):
    """Parse Mercado Livre catalog/item PDPs from structured HTML payload."""

    name = "mercadolivre"
    store, country, currency = "mercadolivre", "BR", "BRL"
    supports_search = True
    allowed_domains = [
        "mercadolivre.com.br",
        "produto.mercadolivre.com.br",
        "lista.mercadolivre.com.br",
    ]
    start_urls: list[str] = []

    def build_search_url(self, query: str) -> str:
        q = quote_plus(query.strip())
        return f"https://lista.mercadolivre.com.br/{q}"

    def parse_search_results(self, response: Response) -> list[SearchCandidate]:
        page_url = str(getattr(response, "url", "") or "")
        html = getattr(response, "text", None) or ""
        if "account-verification" in page_url.casefold() or (
            "account-verification" in html[:8_000].casefold()
            and "ui-search-layout" not in html.casefold()
        ):
            raise RequestError(
                "Mercado Livre exige login/sessão (account-verification); "
                "configure MERCADOLIVRE_AUTH_EMAIL/PASSWORD ou faça seed da sessão",
                code="AUTH_REQUIRED",
                url=page_url or None,
                retryable=True,
            )

        # Prefer titled organic cards; skip carousel/intervention ads that
        # otherwise flood the first N /p/MLB links (Norton, M365, …).
        anchors = response.css(
            "a.poly-component__title, a.ui-search-link, a[href*='/p/MLB']"
        )
        candidates: list[SearchCandidate] = []
        seen: set[str] = set()
        for anchor in anchors:
            href = (anchor.css("::attr(href)").get() or "").strip()
            if not href:
                continue
            absolute = urljoin(response.url, href)
            if "mercadolivre.com.br" not in absolute.casefold():
                continue
            if self._is_serp_noise_url(absolute):
                continue
            path = urlparse(absolute).path or ""
            if "/p/" not in path and "/MLB-" not in path.upper():
                continue
            canonical = canonicalize_url(absolute)
            if canonical in seen:
                continue
            seen.add(canonical)
            title = self._serp_anchor_title(anchor)
            product_id = None
            catalog = _CATALOG_ID_RE.search(path)
            if catalog:
                product_id = catalog.group(1).upper()
            else:
                item = _ITEM_ID_RE.search(path)
                if item:
                    product_id = f"MLB{item.group(1)}"
            candidates.append(
                SearchCandidate(
                    url=absolute,
                    title=title,
                    product_id=product_id,
                    metadata={"source": "mercadolivre-search"},
                )
            )
            if len(candidates) >= 40:
                break
        return candidates

    @staticmethod
    def _is_serp_noise_url(url: str) -> bool:
        folded = url.casefold()
        if "intervention_type=" in folded:
            return True
        # Digital-goods carousels often sit above organic GPU cards.
        if "#intervention" in folded or "intervention_type" in folded:
            return True
        return False

    @staticmethod
    def _serp_anchor_title(anchor: Any) -> str | None:
        title = (anchor.css("::attr(title)").get() or "").strip()
        if MercadoLivreSpider._usable_serp_title(title):
            return title
        texts = [
            t.strip()
            for t in anchor.css("::text").getall()
            if t and t.strip() and t.strip().casefold() not in {"r$", "rs"}
        ]
        joined = " ".join(texts).strip()
        if MercadoLivreSpider._usable_serp_title(joined):
            return joined
        return None

    @staticmethod
    def _usable_serp_title(text: str | None) -> bool:
        if not text or len(text.strip()) < 8:
            return False
        folded = text.strip().casefold()
        if folded in {"r$", "rs"}:
            return False
        # Price / discount fragments from non-title anchors.
        compact = re.sub(r"\s+", "", folded)
        if re.fullmatch(r"[\d\.\,\%xoff\-semjuros]+", compact):
            return False
        letters = sum(1 for ch in folded if ch.isalpha())
        return letters >= 4

    def prepare_fetch_url(self, url: str) -> str:
        """Keep catalog id + item_id filter; drop marketing tracking noise."""
        return canonicalize_url(url)

    def extract_offer(self, response: Response) -> ProductOffer:
        self._ensure_product_page(response)
        json_ld = self.json_ld(response)
        offer_ld = self._offers_object(json_ld)

        price, price_source = self._price(response, offer_ld)
        original_price, original_source = self._original_price(response, price)
        installment_price, installment_count, installment_source = self._installment(
            response
        )
        availability, availability_source = self._availability(offer_ld, response)

        product_id = self._product_id(response, json_ld)
        item_id = self._item_id_from_url(response.url)
        sku = self._string(json_ld.get("sku")) or product_id
        seller = self._seller(response)

        from ...utils.timed_promotion import mercadolivre_lightning_promotion

        promo = mercadolivre_lightning_promotion(
            response.text or "",
            item_id=item_id,
            product_id=product_id,
        )
        metadata: dict[str, Any] = {
            "source": {
                "price": price_source,
                "original_price": original_source,
                "installment": installment_source,
                "availability": availability_source,
                "product_id": "json-ld-or-url",
                "seller": "pdp-dom" if seller else "absent",
                "promotion": promo["source"] if promo else "absent",
            },
            "item_id": item_id,
            "catalog_product_id": product_id,
        }
        if promo:
            metadata["promotion"] = promo

        return ProductOffer(
            store=self.store,
            country=self.country,
            product_id=product_id,
            sku=sku,
            seller=seller,
            url=response.url,
            canonical_url=canonicalize_url(response.url),
            currency=self.currency,
            price=price,
            original_price=original_price,
            discount_percentage=self._discount_percentage(price, original_price),
            pix_price=None,
            installment_price=installment_price,
            installment_count=installment_count,
            available=availability == "available",
            availability=availability,
            metadata=metadata,
        )

    def extract_details(self, response: Response) -> ProductDetails:
        self._ensure_product_page(response)
        json_ld = self.json_ld(response)
        title = self._string(json_ld.get("name")) or self.first(
            response,
            ["h1.ui-pdp-title::text", "h1::text", "title::text"],
        )
        if not title:
            raise ParseError("Título do produto não encontrado")

        product_id = self._product_id(response, json_ld)
        brand = self._brand(json_ld)
        description = self._string(json_ld.get("description"))
        specifications = self._specifications_from_description(description)
        resolved = resolve_product_identity(
            specifications=specifications,
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
            specifications=dict(specifications),
            images=[],
            metadata={
                "source": {
                    "title": "json-ld" if json_ld.get("name") else "dom",
                    "brand": "json-ld" if brand else "title-fallback",
                    "category": resolved.category,
                },
                "item_id": self._item_id_from_url(response.url),
                "description": description,
            },
        )

    def extract_images(self, response: Response) -> list[str]:
        data = self.json_ld(response)
        return self.normalize_image_urls(data.get("image"), base_url=response.url)

    def _ensure_product_page(self, response: Response) -> None:
        text = (response.text or "").casefold()
        if ("verifychallenge" in text and "continue-button" in text) or (
            "snoopy-generation" in text
            and ("continue-button" in text or "_bmc" in text)
        ):
            # Must keep Camoufox / challenge resolution / proxy FALLBACK open.
            raise RequestError(
                "Mercado Livre apresentou challenge Snoopy anti-bot",
                code="UPSTREAM_BLOCKED",
                url=response.url,
            )
        json_ld = self.json_ld(response)
        if json_ld.get("@type") == "Product" or json_ld.get("name"):
            return
        if response.css("h1.ui-pdp-title::text, .ui-pdp-price").get():
            return
        if self._catalog_id_from_url(response.url) or self._item_id_from_url(
            response.url
        ):
            # URL looks like PDP but body has no product signals.
            raise ParseError("HTML do Mercado Livre sem sinais de produto")
        raise ParseError("Página do Mercado Livre não reconhecida como PDP")

    def _product_id(self, response: Response, json_ld: dict[str, Any]) -> str:
        for key in ("sku", "productID", "productId"):
            value = self._string(json_ld.get(key))
            if value and value.upper().startswith("MLB"):
                return value.upper()
        catalog = self._catalog_id_from_url(response.url)
        if catalog:
            return catalog
        item = self._item_id_from_url(response.url)
        if item:
            return item
        raise ParseError("Identificador do produto não encontrado")

    @staticmethod
    def _catalog_id_from_url(url: str) -> str | None:
        match = _CATALOG_ID_RE.search(urlparse(url).path or "")
        return match.group(1).upper() if match else None

    @staticmethod
    def _item_id_from_url(url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        filters = qs.get("pdp_filters") or []
        for raw in filters:
            decoded = unquote(raw)
            match = _ITEM_ID_FILTER_RE.search(decoded)
            if match:
                return match.group(1).upper()
        path = parsed.path or ""
        if "/p/" in path:
            # Prefer explicit item_id query over catalog slug MLB in path.
            return None
        match = _ITEM_ID_RE.search(path)
        if match:
            return f"MLB{match.group(1)}"
        return None

    @staticmethod
    def _offers_object(json_ld: dict[str, Any]) -> dict[str, Any]:
        offers = json_ld.get("offers")
        if isinstance(offers, dict):
            return offers
        if isinstance(offers, list):
            for item in offers:
                if isinstance(item, dict):
                    return item
        return {}

    def _price(
        self, response: Response, offer_ld: dict[str, Any]
    ) -> tuple[Decimal, str]:
        raw = offer_ld.get("price")
        if raw is not None:
            try:
                amount = Decimal(str(raw))
            except (InvalidOperation, ValueError) as exc:
                raise MissingPriceError(f"Preço JSON-LD inválido: {raw!r}") from exc
            if amount <= 0:
                raise MissingPriceError(f"Preço não positivo: {raw!r}")
            return amount, "json-ld"

        meta = self.first(
            response,
            [
                ".ui-pdp-price [itemprop='price']::attr(content)",
                "[itemprop='price']::attr(content)",
            ],
        )
        if meta:
            try:
                amount = Decimal(str(meta).strip())
            except (InvalidOperation, ValueError):
                amount = parse_money(meta, self.currency)
            if amount <= 0:
                raise MissingPriceError(f"Preço não positivo: {meta!r}")
            return amount, "itemprop-price"

        raise MissingPriceError("Preço não encontrado")

    def _original_price(
        self, response: Response, price: Decimal
    ) -> tuple[Decimal | None, str | None]:
        label = response.css(
            ".ui-pdp-price__original-value::attr(aria-label), "
            "s.ui-pdp-price__original-value::attr(aria-label)"
        ).get()
        if label:
            digits = re.findall(
                r"(\d[\d.]*)\s*reais(?:\s*com\s*(\d+)\s*centavos)?", label
            )
            if digits:
                whole, cents = digits[0]
                try:
                    whole_n = Decimal(whole.replace(".", ""))
                    cents_n = Decimal(cents or "0")
                    original = whole_n + (cents_n / Decimal(100))
                except (InvalidOperation, ValueError):
                    original = None
                if original and original > price:
                    return original, "dom-original-aria"
        return None, None

    def _installment(
        self, response: Response
    ) -> tuple[Decimal | None, int | None, str | None]:
        root = response.css("#pricing_price_subtitle")
        text = " ".join(
            t.strip() for t in root.css("::text").getall() if t and t.strip()
        ).replace("\xa0", " ")
        count_match = re.search(r"(\d+)\s*x", text, re.I)
        if not count_match:
            return None, None, None
        count = int(count_match.group(1))
        fraction = root.css(".andes-money-amount__fraction::text").get()
        cents = root.css(".andes-money-amount__cents::text").get()
        if fraction:
            whole = fraction.strip().replace(".", "")
            cent = (cents or "0").strip()
            try:
                installment = Decimal(f"{whole}.{cent}")
            except (InvalidOperation, ValueError):
                installment = None
            if installment and installment > 0:
                return installment, count, "pricing-subtitle"
        match = re.search(r"(\d+[.,]\d+|\d+)", text)
        if not match:
            return None, count, "pricing-subtitle-count-only"
        try:
            installment = parse_money(match.group(1), self.currency)
        except MissingPriceError:
            return None, count, "pricing-subtitle-count-only"
        return installment, count, "pricing-subtitle"

    def _availability(
        self, offer_ld: dict[str, Any], response: Response
    ) -> tuple[Availability, str]:
        raw = str(offer_ld.get("availability") or "").casefold()
        if "outofstock" in raw or "soldout" in raw:
            return "out_of_stock", "json-ld"
        if "instock" in raw or "limitedavailability" in raw:
            return "available", "json-ld"
        if response.css(".ui-pdp-price [itemprop='price']").get():
            return "available", "price-widget"
        return "unavailable", "fallback"

    def _seller(self, response: Response) -> str | None:
        for selector in (
            "button.ui-pdp-seller__link-trigger-button span::text",
            ".ui-pdp-seller__link-trigger span::text",
            ".ui-pdp-seller__link-trigger::text",
            ".ui-pdp-seller__header__title::text",
            "a.ui-pdp-media__action[href*='/loja/']::text",
            "a[href*='/perfil/']::text",
            "[data-testid='seller-info'] a::text",
        ):
            value = self.first(response, [selector])
            if (
                value
                and len(value) < 120
                and value.casefold()
                not in {
                    "ver mais",
                    "mais informações",
                    "mais informacoes",
                }
            ):
                return value
        return None

    @staticmethod
    def _brand(json_ld: dict[str, Any]) -> str | None:
        brand = json_ld.get("brand")
        if isinstance(brand, dict):
            return MercadoLivreSpider._string(brand.get("name"))
        return MercadoLivreSpider._string(brand)

    @staticmethod
    def _specifications_from_description(description: str | None) -> dict[str, str]:
        if not description:
            return {}
        specs: dict[str, str] = {}
        for part in description.split("|"):
            chunk = part.strip()
            if ":" not in chunk:
                continue
            key, value = chunk.split(":", 1)
            key_n = key.strip()
            value_n = value.strip()
            if key_n and value_n:
                specs[key_n] = value_n
        return specs

    @staticmethod
    def _discount_percentage(
        price: Decimal, original: Decimal | None
    ) -> Decimal | None:
        if original is None or original <= price:
            return None
        return ((original - price) / original * Decimal(100)).quantize(Decimal("0.01"))

    @staticmethod
    def _string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
