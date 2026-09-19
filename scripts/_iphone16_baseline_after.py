"""Post-fix iPhone 16 match baseline (BR stores first)."""

from __future__ import annotations

import json
from pathlib import Path

from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.matching.identity import (
    build_search_queries,
    identity_from_price_item,
)
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.schemas import MatchRequest

REF = (
    "https://www.magazineluiza.com.br/apple-iphone-16-128gb-preto-61-48mp-ios-5g/"
    "p/238803400/te/ip16/?seller_id=magazineluiza"
)
# Prioritize stores where ground truth confirmed the same SKU.
STORES = ["kabum", "amazon_br", "magazineluiza"]
OUT = Path("/tmp/_iphone16_after.json")


def main() -> None:
    scrape = ProductScrapeService()
    ref = scrape.scrape(REF, include_images=False)
    ident = identity_from_price_item(ref)
    svc = ProductMatchService(scrape_service=scrape)
    resp = svc.match(
        MatchRequest(
            reference_url=REF,
            stores=STORES,
            persist=False,
            include_review=True,
            max_candidates_per_store=5,
        )
    )
    payload = {
        "reference": {
            "store": ref.store,
            "title": ref.title,
            "brand": ref.brand,
            "model": ref.model,
            "variant": ref.variant,
            "variant_attrs": ident.variant_attrs,
            "queries": build_search_queries(ident),
        },
        "matches": [
            {
                "store": hit.store,
                "decision": hit.decision,
                "confidence": str(hit.confidence),
                "title": hit.product.title,
                "variant": hit.product.variant,
                "url": hit.product.url,
                "query": hit.search_query,
                "reasons": [
                    {"code": r.code, "detail": r.detail, "score": r.score}
                    for r in hit.reasons
                ],
            }
            for hit in resp.matches
        ],
        "unmatched": resp.unmatched_stores,
        "errors": [
            {"store": e.store, "code": e.code, "message": e.message}
            for e in resp.errors
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        OUT.write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text)


if __name__ == "__main__":
    main()
