"""Per-store search probe (flush stdout); skip full match scrape storm."""

from __future__ import annotations

import json
import sys
import time

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
    get_shared_html_fetcher,
)
from scout_api.modules.matching.identity import (
    build_search_queries,
    identity_from_price_item,
)
from scout_api.modules.matching.store_search_service import StoreSearchService


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    get_shared_html_fetcher.cache_clear()
    stores = sys.argv[1:] or [
        "shoppingchina",
        "nissei",
        "shopee",
        "bestbuy",
        "amazon_us",
    ]
    scrape = ProductScrapeService()
    log("scraping reference…")
    ref = scrape.scrape(
        "https://www.magazineluiza.com.br/apple-iphone-16-128gb-preto-61-48mp-ios-5g/"
        "p/238803400/te/ip16/?seller_id=magazineluiza",
        include_images=False,
    )
    ident = identity_from_price_item(ref)
    queries = build_search_queries(ident)[:2]
    log(f"queries={queries}")
    search = StoreSearchService()
    results: dict[str, object] = {}
    for store in stores:
        log(f"=== {store} ===")
        time.sleep(3)
        entry: dict[str, object] = {"ok": False}
        for query in queries:
            try:
                hits = search.search(store, query, limit=5)
                entry = {
                    "ok": True,
                    "query": query,
                    "count": len(hits),
                    "hits": [
                        {
                            "id": h.product_id,
                            "title": (h.title or "")[:100],
                            "url": h.url,
                        }
                        for h in hits
                    ],
                }
                log(f"{store}: {len(hits)} hits via {query!r}")
                if hits:
                    break
                # Empty SERP — try next progressive query.
            except RequestError as exc:
                entry = {
                    "ok": False,
                    "query": query,
                    "error": exc.code,
                    "message": str(exc)[:220],
                }
                log(f"{store}: {exc.code} on {query!r}")
            except ParseError as exc:
                entry = {
                    "ok": False,
                    "query": query,
                    "error": "PARSE_ERROR",
                    "message": str(exc)[:220],
                }
                log(f"{store}: PARSE_ERROR on {query!r}")
            except Exception as exc:  # noqa: BLE001
                entry = {
                    "ok": False,
                    "query": query,
                    "error": type(exc).__name__,
                    "message": str(exc)[:220],
                }
                log(f"{store}: {type(exc).__name__} on {query!r}")
        results[store] = entry
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
