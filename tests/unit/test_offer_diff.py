"""Unit tests for offer fingerprinting and diff events."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scout_api.modules.crawler.models.product import ProductOffer
from scout_api.modules.matching.offer_diff import diff_offers, fingerprint_from_offer


def _offer(**kwargs: object) -> ProductOffer:
    defaults: dict[str, object] = {
        "store": "kabum",
        "country": "BR",
        "product_id": "123",
        "url": "https://www.kabum.com.br/produto/123",
        "canonical_url": "https://www.kabum.com.br/produto/123",
        "currency": "BRL",
        "price": Decimal("199.90"),
        "seller": "Kabum",
        "availability": "available",
        "available": True,
        "scraped_at": datetime(2026, 9, 14, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return ProductOffer(**defaults)  # type: ignore[arg-type]


def test_fingerprint_stable() -> None:
    a = fingerprint_from_offer(_offer())
    b = fingerprint_from_offer(_offer())
    assert a == b


def test_price_change_event() -> None:
    previous = {
        "fingerprint": fingerprint_from_offer(_offer()),
        "price": "199.90",
        "currency": "BRL",
        "seller": "Kabum",
        "availability": "available",
        "available": True,
    }
    current = _offer(price=Decimal("179.90"))
    diff = diff_offers(previous, current)
    assert "price_changed" in diff.events
    assert "unchanged" not in diff.events


def test_seller_change_event() -> None:
    previous = {
        "fingerprint": fingerprint_from_offer(_offer()),
        "price": "199.90",
        "currency": "BRL",
        "seller": "Kabum",
        "availability": "available",
        "available": True,
    }
    current = _offer(seller="Marketplace Seller")
    diff = diff_offers(previous, current)
    assert "seller_changed" in diff.events


def test_removed_and_blocked() -> None:
    assert diff_offers({"fingerprint": "x"}, None, removed=True).events == (
        "offer_removed",
    )
    assert diff_offers({"fingerprint": "x"}, None, scrape_failed=True).events == (
        "scrape_failed",
    )


def test_out_of_stock_event() -> None:
    previous = {
        "fingerprint": fingerprint_from_offer(_offer()),
        "price": "199.90",
        "currency": "BRL",
        "seller": "Kabum",
        "availability": "available",
        "available": True,
    }
    current = _offer(availability="out_of_stock", available=False)
    diff = diff_offers(previous, current)
    assert "availability_changed" in diff.events
    assert "out_of_stock" in diff.events
