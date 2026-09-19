"""Live validation of remaining match stores for iPhone 16 128GB Preto."""

from __future__ import annotations

import json
import time

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.matching.identity import (
    build_search_queries,
    identity_from_price_item,
)
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.schemas import MatchRequest
from scout_api.modules.matching.store_search_service import StoreSearchService

REF = (
    "https://www.magazineluiza.com.br/apple-iphone-16-128gb-preto-61-48mp-ios-5g/"
    "p/238803400/te/ip16/?seller_id=magazineluiza"
)
STORES = [
    "shopee",
    "bestbuy",
    "nissei",
    "shoppingchina",
    "amazon_us",
]


def main() -> None:
    # Bust shared fetcher cache so hot-patched modules apply.
    from scout_api.modules.crawler.services import product_scrape_service as pss

    pss.get_shared_html_fetcher.cache_clear()

    scrape = ProductScrapeService()
    ref = scrape.scrape(REF, include_images=False)
    ident = identity_from_price_item(ref)
    queries = build_search_queries(ident)[:3]
    search = StoreSearchService()

    retrieval: dict[str, object] = {}
    for store in STORES:
        store_rows: list[dict[str, object]] = []
        for query in queries:
            try:
                hits = search.search(store, query, limit=5)
                store_rows.append(
                    {
                        "query": query,
                        "count": len(hits),
                        "titles": [
                            {"id": h.product_id, "title": (h.title or "")[:90]}
                            for h in hits[:5]
                        ],
                    }
                )
                if hits:
                    break
            except RequestError as exc:
                store_rows.append(
                    {"query": query, "error": exc.code, "message": str(exc)[:180]}
                )
            except ParseError as exc:
                store_rows.append(
                    {"query": query, "error": "PARSE_ERROR", "message": str(exc)[:180]}
                )
            time.sleep(2)
        retrieval[store] = store_rows

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
        "queries": queries,
        "retrieval": retrieval,
        "matches": [
            {
                "store": hit.store,
                "decision": hit.decision,
                "confidence": str(hit.confidence),
                "title": hit.product.title,
                "url": hit.product.url,
                "query": hit.search_query,
                "reasons": [r.code for r in hit.reasons],
            }
            for hit in resp.matches
        ],
        "unmatched": resp.unmatched_stores,
        "errors": [
            {"store": e.store, "code": e.code, "message": e.message[:200]}
            for e in resp.errors
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
