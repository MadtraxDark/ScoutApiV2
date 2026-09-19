"""Live match: Visão VIP RTX 5070 Shadow → all search-capable stores."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scout_api.modules.crawler.core.scrape_guard import ScrapeGuard
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
    get_shared_html_fetcher,
)
from scout_api.modules.crawler.services.store_resolver import stores_supporting_search
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.schemas import MatchRequest

REF = (
    "https://visaovip.com/prod/placas-de-video-nvidia/"
    "placa-de-video-msi-shadow-3x-oc-12gb-geforce-rtx5070-gddr7-912-v532-232/55359/"
)
OUT = Path("/tmp/visaovip_rtx5070_match.json")

get_shared_html_fetcher.cache_clear()
guard = ScrapeGuard(
    url_cooldown_seconds=0,
    domain_min_interval_seconds=2,
    result_cache_ttl_seconds=0,
)
scrape = ProductScrapeService(guard=guard)
svc = ProductMatchService(scrape_service=scrape)

print("REF_SCRAPE", flush=True)
t0 = time.time()
ref = scrape.scrape(REF, include_images=False)
print(
    json.dumps(
        {
            "secs": round(time.time() - t0, 1),
            "store": ref.store,
            "title": ref.title,
            "brand": ref.brand,
            "model": ref.model,
            "sku": ref.sku,
            "gtin": ref.gtin,
            "price": str(ref.price),
            "currency": ref.currency,
            "available": ref.available,
        },
        ensure_ascii=False,
    ),
    flush=True,
)

stores = list(stores_supporting_search())
print("STORES", stores, flush=True)

print("MATCH_ALL", flush=True)
t1 = time.time()
resp = svc.match(
    MatchRequest(
        reference_url=REF,
        stores=stores,
        persist=False,
        include_review=True,
        max_candidates_per_store=5,
    )
)

payload = {
    "secs": round(time.time() - t1, 1),
    "reference": {
        "store": ref.store,
        "title": ref.title,
        "sku": ref.sku,
        "price": str(ref.price),
        "currency": ref.currency,
        "url": REF,
    },
    "matches": [
        {
            "store": h.store,
            "country": h.country,
            "decision": h.decision,
            "confidence": str(h.confidence),
            "title": (h.product.title or "")[:120],
            "price": str(h.product.price),
            "currency": h.product.currency,
            "sku": h.product.sku,
            "brand": h.product.brand,
            "model": h.product.model,
            "available": h.product.available,
            "url": h.product.url,
            "reasons": [{"code": r.code, "detail": r.detail} for r in h.reasons],
        }
        for h in resp.matches
    ],
    "unmatched_stores": resp.unmatched_stores,
    "errors": [
        {"store": e.store, "code": e.code, "message": (e.message or "")[:200]}
        for e in resp.errors
    ],
}
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
print("WROTE", OUT, flush=True)
