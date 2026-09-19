"""Score Shopping China Black 128GB vs Magalu ref."""

from __future__ import annotations

import json

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
    get_shared_html_fetcher,
)
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.identity import (
    build_search_queries,
    identity_from_price_item,
)
from scout_api.modules.matching.store_search_service import StoreSearchService

REF = (
    "https://www.magazineluiza.com.br/apple-iphone-16-128gb-preto-61-48mp-ios-5g/"
    "p/238803400/te/ip16/?seller_id=magazineluiza"
)
SC = (
    "https://www.shoppingchina.com.py/produto/"
    "celular-apple-iphone-16-a3287-128gb-black-sim-948623"
)


def main() -> None:
    get_shared_html_fetcher.cache_clear()
    scrape = ProductScrapeService()
    ref = scrape.scrape(REF, include_images=False)
    ref_i = identity_from_price_item(ref)
    print("queries", build_search_queries(ref_i)[:5], flush=True)
    search = StoreSearchService()
    for q in build_search_queries(ref_i)[:4]:
        hits = search.search("shoppingchina", q, limit=5)
        print(f"SERP {q!r} -> {len(hits)}", flush=True)
        for h in hits:
            print(" ", h.product_id, (h.title or "")[:70], flush=True)
        if hits:
            break
    try:
        sc = scrape.scrape(SC, include_images=False)
    except (RequestError, ParseError) as exc:
        print("SCRAPE_FAIL", getattr(exc, "code", type(exc).__name__), exc, flush=True)
        return
    sc_i = identity_from_price_item(sc)
    score = MatchingEngine().score(ref_i, sc_i)
    print(
        json.dumps(
            {
                "sc_title": sc.title,
                "sc_brand": sc.brand,
                "sc_model": sc.model,
                "sc_variant": sc.variant,
                "sc_attrs": sc_i.variant_attrs,
                "decision": score.decision,
                "reasons": [
                    {"code": r.code, "detail": r.detail} for r in score.reasons
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
