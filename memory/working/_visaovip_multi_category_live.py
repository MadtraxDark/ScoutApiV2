"""Live multi-category Visão VIP search smoke (generic queries, no SKU hardcodes)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scout_api.modules.crawler.services.product_scrape_service import (
    get_shared_html_fetcher,
)
from scout_api.modules.matching.store_search_service import StoreSearchService

# Diverse catalog queries — prove search works beyond one motherboard.
QUERIES = [
    ("motherboard", "ASUS TUF Gaming B650M-E WIFI"),
    ("cpu", "Ryzen 7 5800X3D"),
    ("gpu", "RTX 5070"),
    ("memory", "Kingston Fury DDR5"),
    ("ssd", "Samsung 990 PRO"),
]
OUT = Path("memory/working/visaovip_multi_category_live.json")


def main() -> None:
    get_shared_html_fetcher.cache_clear()
    search = StoreSearchService()
    rows = []
    for category, query in QUERIES:
        t0 = time.perf_counter()
        try:
            cands = search.search("visaovip", query, limit=5)
            err = None
        except Exception as exc:  # noqa: BLE001 — live smoke aggregates errors
            cands = []
            err = f"{type(exc).__name__}: {exc}"
        ms = int((time.perf_counter() - t0) * 1000)
        rows.append(
            {
                "category": category,
                "query": query,
                "ms": ms,
                "count": len(cands),
                "error": err,
                "candidates": [
                    {
                        "product_id": c.product_id,
                        "title": c.title,
                        "url": c.url,
                    }
                    for c in cands[:5]
                ],
            }
        )
        print(
            f"{category}: count={len(cands)} ms={ms} err={err}",
            flush=True,
        )
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT, flush=True)


if __name__ == "__main__":
    main()
