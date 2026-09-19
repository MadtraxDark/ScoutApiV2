"""Docker-friendly live rediscovery (paths under /app)."""

from __future__ import annotations

import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

from scout_api.modules.crawler.services.product_scrape_service import (  # noqa: E402
    ProductScrapeService,
)
from scout_api.modules.matching.identity import (  # noqa: E402
    build_search_queries,
    identity_from_price_item,
)
from scout_api.modules.matching.product_match_service import (  # noqa: E402
    ProductMatchService,
)
from scout_api.modules.matching.schemas import MatchRequest  # noqa: E402
from scout_api.modules.matching.store_search_service import (  # noqa: E402
    StoreSearchService,
)

REF_URL = (
    "https://visaovip.com/prod/placas-de-video-nvidia/"
    "placa-de-video-msi-shadow-3x-oc-12gb-geforce-rtx5070-gddr7-912-v532-232/55359/"
)
STORES = ["kabum", "magazineluiza"]
KABUM_ID = "777166"
MAGALU_ID = "fkff6cf4a2"


def main() -> int:
    scrape = ProductScrapeService()
    search = StoreSearchService()
    ref = scrape.scrape(REF_URL)
    identity = identity_from_price_item(ref)
    queries = build_search_queries(identity)
    print("QUERIES", json.dumps(queries, ensure_ascii=False), flush=True)

    matcher = ProductMatchService(scrape_service=scrape, search_service=search)
    resp = matcher.match(
        MatchRequest(
            reference_url=REF_URL,
            stores=STORES,
            persist=False,
            max_candidates_per_store=5,
        )
    )
    matches = []
    for m in resp.matches:
        matches.append(
            {
                "store": m.store,
                "product_id": m.product.product_id,
                "url": m.product.url,
                "title": m.product.title,
                "decision": m.decision,
                "confidence": str(m.confidence),
                "search_query": m.search_query,
                "reasons": [
                    {"code": r.code, "detail": r.detail, "score": r.score}
                    for r in m.reasons
                ],
            }
        )
    out = {
        "queries": queries,
        "matches": matches,
        "unmatched": list(resp.unmatched_stores),
        "errors": [
            {"store": e.store, "code": e.code, "message": e.message}
            for e in resp.errors
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
    kabum_ok = any(
        m["store"] == "kabum"
        and (
            KABUM_ID in (m["product_id"] or "", m["url"] or "")
            or (
                m["decision"] == "auto_match"
                and "shadow" in (m["title"] or "").casefold()
                and "5070" in (m["title"] or "")
                and "ti" not in (m["title"] or "").casefold()
            )
        )
        for m in matches
    )
    magalu_ok = any(
        m["store"] == "magazineluiza"
        and m["decision"] == "auto_match"
        and (
            MAGALU_ID in (m["product_id"] or "", m["url"] or "")
            or (
                "shadow" in (m["title"] or "").casefold()
                and "5070" in (m["title"] or "")
                and "ti" not in (m["title"] or "").casefold()
            )
        )
        for m in matches
    )
    print(f"RESULT kabum_ok={kabum_ok} magalu_ok={magalu_ok}", flush=True)
    return 0 if kabum_ok and magalu_ok else 1


if __name__ == "__main__":
    sys.exit(main())
