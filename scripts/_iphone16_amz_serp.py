"""Diagnose Amazon BR SERP for iPhone 16 128GB Preto."""

from __future__ import annotations

import json

from scout_api.modules.matching.store_search_service import StoreSearchService

QUERIES = [
    "apple iphone 16 128gb preto",
    "apple iphone 16 128gb black",
    "apple iphone 16 128gb",
    "iphone 16 128gb",
]


def main() -> None:
    search = StoreSearchService()
    out: dict[str, list[dict[str, str | None]]] = {}
    for query in QUERIES:
        try:
            hits = search.search("amazon_br", query, limit=8)
            out[query] = [
                {"title": h.title, "url": h.url, "product_id": h.product_id}
                for h in hits
            ]
        except Exception as exc:  # noqa: BLE001 — diagnostic only
            out[query] = [{"error": f"{type(exc).__name__}: {exc}"}]
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
