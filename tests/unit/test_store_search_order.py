"""Unit tests for GTIN-first live-search store ordering."""

from __future__ import annotations

from scout_api.modules.matching.store_search_order import (
    order_stores_for_match,
    split_stores_for_match_waves,
)


def test_split_stores_for_match_waves_gtin_first() -> None:
    wave1, wave2, wave3 = split_stores_for_match_waves(
        [
            "kabum",
            "bestbuy",
            "amazon_br",
            "amazon_us",
            "magazineluiza",
            "shopee",
            "mercadolivre",
        ]
    )
    # Dominant locale pt-BR: GTIN serial, then parallel remainder.
    assert wave1 == ["kabum", "amazon_br"]
    assert wave2 == ["magazineluiza", "mercadolivre", "shopee"]
    # en-US GTIN stores deferred to wave3 (avoid mid-match locale thrash).
    assert wave3 == ["bestbuy", "amazon_us"]


def test_split_stores_preserves_locale_coherent_waves() -> None:
    wave1, wave2, wave3 = split_stores_for_match_waves(
        ["amazon_us", "kabum", "shopee", "nissei", "pichau"]
    )
    assert wave1 == ["kabum"]
    assert wave2 == ["shopee", "pichau"]
    assert wave3 == ["nissei", "amazon_us"]


def test_gtin_rich_stores_come_before_marketplace() -> None:
    ordered = order_stores_for_match(
        ["shopee", "magazineluiza", "kabum", "amazon_br", "bestbuy"],
        reference_store="magazineluiza",
        reference_has_gtin=False,
    )
    assert ordered[0] == "kabum"
    # pt-BR cluster before en-US (bestbuy), even when Best Buy has better GTIN rank.
    assert ordered.index("amazon_br") < ordered.index("bestbuy")
    assert ordered.index("amazon_br") < ordered.index("shopee")
    # Reference without GTIN is pushed after peers that may expose a barcode.
    assert ordered[-1] == "magazineluiza"


def test_locale_affinity_groups_pt_br_before_en_us() -> None:
    ordered = order_stores_for_match(
        ["amazon_us", "nissei", "kabum", "bestbuy", "amazon_br"],
        reference_has_gtin=True,
    )
    assert ordered.index("kabum") < ordered.index("nissei")
    assert ordered.index("amazon_br") < ordered.index("nissei")
    assert ordered.index("nissei") < ordered.index("amazon_us")
    assert max(ordered.index("amazon_us"), ordered.index("bestbuy")) > ordered.index(
        "nissei"
    )


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
