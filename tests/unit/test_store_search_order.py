"""Unit tests for GTIN-first live-search store ordering."""

from __future__ import annotations

from scout_api.modules.matching.store_search_order import order_stores_for_match


def test_gtin_rich_stores_come_before_marketplace() -> None:
    ordered = order_stores_for_match(
        ["shopee", "magazineluiza", "kabum", "amazon_br", "bestbuy"],
        reference_store="magazineluiza",
        reference_has_gtin=False,
    )
    assert ordered[0] == "kabum"
    assert ordered[1] == "bestbuy"
    assert ordered.index("amazon_br") < ordered.index("shopee")
    # Reference without GTIN is pushed after peers that may expose a barcode.
    assert ordered[-1] == "magazineluiza"


def test_reference_not_deprioritized_when_gtin_already_known() -> None:
    ordered = order_stores_for_match(
        ["shopee", "kabum", "magazineluiza"],
        reference_store="magazineluiza",
        reference_has_gtin=True,
    )
    assert ordered == ["kabum", "magazineluiza", "shopee"]


def test_explicit_subset_is_reordered_not_expanded() -> None:
    ordered = order_stores_for_match(
        ["shopee", "amazon_br"],
        reference_store="shopee",
        reference_has_gtin=False,
    )
    assert ordered == ["amazon_br", "shopee"]


def test_dedupes_and_normalizes_keys() -> None:
    ordered = order_stores_for_match(
        ["Kabum", "kabum", " BestBuy "],
        reference_has_gtin=True,
    )
    assert ordered == ["kabum", "bestbuy"]
