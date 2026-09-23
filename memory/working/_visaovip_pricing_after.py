"""Post-change Visão VIP pricing regression (ADATA crawl + Match SERP + multi-cat)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.offer_scrape_service import OfferScrapeService
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
    get_shared_html_fetcher,
)
from scout_api.modules.matching.store_search_service import StoreSearchService

OUT = Path("memory/working/visaovip_pricing_after.json")
ADATA_URL = (
    "https://www.visaovip.com/prod/memoria-ram-pc/"
    "memoria-ram-adata-xpg-spectrix-d35g-ddr4-8gb-3200mhz-rgb-preto-ax4u32008g16a-sbkd35g/43764/"
)
GT_MARKER = "/41749/"

MULTI = [
    ("memory", "Kingston Fury DDR5"),
    ("motherboard", "ASUS TUF Gaming B650M-E WIFI"),
    ("cpu", "Ryzen 7 5800X3D"),
    ("gpu", "RTX 5070"),
    ("ssd", "Samsung 990 PRO"),
]


def main() -> None:
    get_shared_html_fetcher.cache_clear()
    guard = ScrapeGuard(
        url_cooldown_seconds=0,
        domain_min_interval_seconds=1,
        result_cache_ttl_seconds=0,
    )
    scrape = ProductScrapeService(guard=guard)
    offer_svc = OfferScrapeService(guard=guard)
    search = StoreSearchService()

    payload: dict = {"phase": "after"}

    t0 = time.perf_counter()
    item = scrape.scrape(ADATA_URL, include_images=True)
    crawl_ms = round((time.perf_counter() - t0) * 1000)
    payload["adata_crawl"] = {
        "ms": crawl_ms,
        "product_id": item.product_id,
        "sku": item.sku,
        "title": item.title,
        "brand": item.brand,
        "model": item.model,
        "currency": item.currency,
        "price": str(item.price),
        "pix_price": str(item.pix_price) if item.pix_price is not None else None,
        "original_price": (
            str(item.original_price) if item.original_price is not None else None
        ),
        "images_count": len(item.images or []),
        "display_prices": (item.metadata or {}).get("display_prices"),
        "source": (item.metadata or {}).get("source"),
    }

    t1 = time.perf_counter()
    refreshed = offer_svc.scrape_offer(ADATA_URL)
    refresh_ms = round((time.perf_counter() - t1) * 1000)
    payload["offer_refresh"] = {
        "ms": refresh_ms,
        "price": str(refreshed.price),
        "currency": refreshed.currency,
        "pix_price": (
            str(refreshed.pix_price) if refreshed.pix_price is not None else None
        ),
        "display_prices": (refreshed.metadata or {}).get("display_prices"),
    }

    t2 = time.perf_counter()
    board = search.search("visaovip", "ASUS TUF Gaming B650M-E WIFI", limit=8)
    board_ms = round((time.perf_counter() - t2) * 1000)
    payload["match_serp"] = {
        "ms": board_ms,
        "count": len(board),
        "gt_discovered": any(GT_MARKER in (c.url or "") for c in board),
        "candidates": [
            {"title": c.title, "url": c.url, "product_id": c.product_id} for c in board
        ],
    }

    multi = []
    for category, query in MULTI:
        t = time.perf_counter()
        try:
            cands = search.search("visaovip", query, limit=5)
            err = None
        except Exception as exc:  # noqa: BLE001 — capture live smoke errors
            cands = []
            err = f"{type(exc).__name__}: {exc}"
        multi.append(
            {
                "category": category,
                "query": query,
                "ms": round((time.perf_counter() - t) * 1000),
                "count": len(cands),
                "error": err,
                "first_url": cands[0].url if cands else None,
                "first_id": cands[0].product_id if cands else None,
            }
        )
    payload["multi_category_serp"] = multi

    # Parse one PDP per category when a candidate exists.
    pdp_smoke = []
    for row in multi:
        url = row.get("first_url")
        if not url:
            continue
        t = time.perf_counter()
        try:
            offer = offer_svc.scrape_offer(url)
            pdp_smoke.append(
                {
                    "category": row["category"],
                    "ms": round((time.perf_counter() - t) * 1000),
                    "product_id": offer.product_id,
                    "price": str(offer.price),
                    "currency": offer.currency,
                    "pix_price": (
                        str(offer.pix_price) if offer.pix_price is not None else None
                    ),
                    "display_prices": (offer.metadata or {}).get("display_prices"),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            pdp_smoke.append(
                {
                    "category": row["category"],
                    "ms": round((time.perf_counter() - t) * 1000),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    payload["multi_category_pdp"] = pdp_smoke

    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(payload["adata_crawl"], indent=2, ensure_ascii=False))
    print("gt_discovered", payload["match_serp"]["gt_discovered"])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
