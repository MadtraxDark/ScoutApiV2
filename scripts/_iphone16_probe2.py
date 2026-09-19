"""Quick identity probe for iPhone 16 color gate (host)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.identity import (
    ProductIdentity,
    build_search_queries,
    identity_from_price_item,
    normalize_title,
)


def item(**kw: object) -> ProductPriceItem:
    base: dict[str, object] = {
        "store": "magazineluiza",
        "country": "BR",
        "product_id": "238803400",
        "url": "https://www.magazineluiza.com.br/p/238803400/",
        "canonical_url": "https://www.magazineluiza.com.br/p/238803400/",
        "currency": "BRL",
        "price": Decimal("4500"),
        "scraped_at": datetime(2026, 9, 19, tzinfo=UTC),
        "title": "x",
    }
    base.update(kw)
    return ProductPriceItem.model_validate(base)


def main() -> None:
    ref = identity_from_price_item(
        item(
            title='Apple iPhone 16 128GB Preto 6,1" 48MP iOS 5G',
            brand="Apple",
            model="iPhone 16",
            variant="Preto",
        )
    )
    print("REF", ref.variant_attrs, build_search_queries(ref)[:6])
    teal = identity_from_price_item(
        item(
            store="amazon",
            product_id="B0DJFSTQHX",
            title="Apple iPhone 16 (128 GB) – Verde-acinzentado",
            brand="Apple",
            model="iPhone 16",
            url="https://www.amazon.com.br/dp/B0DJFSTQHX",
            canonical_url="https://www.amazon.com.br/dp/B0DJFSTQHX",
            variant="tamanho: 128 GB; cor: Verde-Acizentado",
        )
    )
    print("TEAL", teal.variant_attrs, MatchingEngine().score(ref, teal).decision)
    black = identity_from_price_item(
        item(
            store="amazon",
            product_id="B0DJFTJ6LX",
            title="Apple iPhone 16 (128 GB) – Preto",
            brand="Apple",
            model="iPhone 16",
            url="https://www.amazon.com.br/dp/B0DJFTJ6LX",
            canonical_url="https://www.amazon.com.br/dp/B0DJFTJ6LX",
            variant="tamanho: 128 GB; cor: Preto",
        )
    )
    print("BLACK", black.variant_attrs, MatchingEngine().score(ref, black).decision)
    ssd_ref = ProductIdentity(
        gtin=None,
        brand="samsung",
        model="990evoplus",
        title="SSD Samsung 990 EVO Plus 1TB",
        title_normalized=normalize_title("SSD Samsung 990 EVO Plus 1TB"),
        variant_attrs={"storage": "1tb"},
        mpn="mzv9s1t0bam",
        mpn_display="MZ-V9S1T0B/AM",
    )
    ssd_bad = ProductIdentity(
        gtin=None,
        brand="samsung",
        model="870evo",
        title="Samsung 870 EVO 1TB",
        title_normalized=normalize_title("Samsung 870 EVO 1TB"),
        variant_attrs={"storage": "1tb"},
    )
    print("SSD", MatchingEngine().score(ssd_ref, ssd_bad).decision)


if __name__ == "__main__":
    main()
