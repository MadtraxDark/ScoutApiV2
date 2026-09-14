"""Unit tests for trusted GTIN learning during matching."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.matching.gtin_learning import (
    resolve_trusted_gtin,
)
from scout_api.modules.matching.identity import (
    ProductIdentity,
    normalize_gtin,
)
from scout_api.modules.matching.schemas import MatchHit, MatchReason


def _item(**kwargs: object) -> ProductPriceItem:
    defaults: dict[str, object] = {
        "store": "kabum",
        "country": "BR",
        "product_id": "1",
        "title": "Apple iPhone 17 256GB Preto",
        "brand": "Apple",
        "model": "iPhone 17",
        "url": "https://www.kabum.com.br/produto/1",
        "canonical_url": "https://www.kabum.com.br/produto/1",
        "currency": "BRL",
        "price": Decimal("6000.00"),
        "scraped_at": datetime(2026, 9, 14, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return ProductPriceItem(**defaults)  # type: ignore[arg-type]


def _identity(**kwargs: object) -> ProductIdentity:
    defaults: dict[str, object] = {
        "gtin": None,
        "brand": "apple",
        "model": "iphone17",
        "title": "Apple iPhone 17 256GB Preto",
        "title_normalized": "apple iphone 17 256gb preto",
        "variant_attrs": {"color": "preto", "storage": "256gb"},
        "store": "magazineluiza",
        "product_id": "241268000",
        "price": Decimal("6332.22"),
        "currency": "BRL",
    }
    defaults.update(kwargs)
    return ProductIdentity(**defaults)  # type: ignore[arg-type]


def _hit(
    *,
    decision: str,
    gtin: str | None,
    store: str = "kabum",
    brand: str = "Apple",
) -> MatchHit:
    return MatchHit(
        store=store,
        country="BR",
        decision=decision,  # type: ignore[arg-type]
        confidence=Decimal("0.9700"),
        reasons=[MatchReason(code="brand_model_exact", detail="x", score=1.0)],
        product=_item(store=store, gtin=gtin, brand=brand),
    )


def test_learn_gtin_from_auto_match_when_reference_missing() -> None:
    gtin = normalize_gtin("7891991010863")
    assert gtin is not None
    trusted = resolve_trusted_gtin(
        _identity(gtin=None),
        [_hit(decision="auto_match", gtin=gtin)],
    )
    assert trusted is not None
    assert trusted.gtin == gtin
    assert trusted.source.startswith("auto_match:")


def test_ignore_gtin_from_review_only() -> None:
    gtin = normalize_gtin("7891991010863")
    trusted = resolve_trusted_gtin(
        _identity(gtin=None),
        [_hit(decision="review", gtin=gtin)],
    )
    assert trusted is None


def test_conflict_across_auto_matches_yields_none() -> None:
    a = normalize_gtin("7891991010863")
    # Build another valid EAN-13
    from scout_api.modules.matching.identity import gtin_check_digit

    body = "789199101087"
    b = body + gtin_check_digit(body)
    assert normalize_gtin(b) == b
    trusted = resolve_trusted_gtin(
        _identity(gtin=None),
        [
            _hit(decision="auto_match", gtin=a, store="kabum"),
            _hit(decision="auto_match", gtin=b, store="amazon"),
        ],
    )
    assert trusted is None


def test_brand_mismatch_blocks_learning() -> None:
    gtin = normalize_gtin("7891991010863")
    trusted = resolve_trusted_gtin(
        _identity(gtin=None, brand="apple"),
        [_hit(decision="auto_match", gtin=gtin, brand="Samsung")],
    )
    assert trusted is None


def test_reference_gtin_preferred_as_consensus() -> None:
    gtin = normalize_gtin("7891991010863")
    trusted = resolve_trusted_gtin(
        _identity(gtin=gtin),
        [_hit(decision="auto_match", gtin=gtin, store="kabum")],
    )
    assert trusted is not None
    assert trusted.gtin == gtin
