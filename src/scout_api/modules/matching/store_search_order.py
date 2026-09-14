"""Order live-search targets so GTIN-rich stores run first.

When the reference listing has no trusted barcode, discovering a check-digit-valid
GTIN early (via ``auto_match``) lets remaining SERPs switch to GTIN-first queries.
"""

from __future__ import annotations

# Lower rank → search earlier. Based on how often PDPs expose GTIN/EAN/UPC
# in our spiders (structured data / specs), not on marketplace popularity.
GTIN_EXPOSURE_RANK: dict[str, int] = {
    "kabum": 10,  # EAN / código de barras in technicalInformation
    "bestbuy": 20,  # UPC / gtin* in product JSON frequently
    "nissei": 30,  # UPC attribute on PDP
    "shoppingchina": 40,  # flix EAN hooks when present
    "amazon_br": 50,  # detail tables / JSON-LD sometimes
    "amazon_us": 55,
    "magazineluiza": 70,  # extractor exists; often absent on PDP
    "shopee": 90,  # marketplace; barcode often missing
}

_DEFAULT_RANK = 100


def gtin_exposure_rank(store_key: str) -> int:
    return GTIN_EXPOSURE_RANK.get(store_key.strip().lower(), _DEFAULT_RANK)


def order_stores_for_match(
    stores: list[str],
    *,
    reference_store: str | None = None,
    reference_has_gtin: bool = False,
) -> list[str]:
    """Return stores ordered for precision-first discovery.

    - Prefer stores that typically publish GTIN/EAN/UPC.
    - If the reference still lacks a barcode, push the reference store later
      (its PDP was already scraped without GTIN).
    """
    seen: set[str] = set()
    unique: list[str] = []
    for raw in stores:
        key = raw.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(key)

    ref = (reference_store or "").strip().lower() or None

    def sort_key(store: str) -> tuple[int, int, str]:
        deprioritize_ref = (
            1 if (not reference_has_gtin and ref is not None and store == ref) else 0
        )
        return (deprioritize_ref, gtin_exposure_rank(store), store)

    return sorted(unique, key=sort_key)
