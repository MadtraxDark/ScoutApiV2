"""Live smoke: Visão VIP Strategy A via Camoufox browser_post (PENDING-018).

Usage:
  docker compose run --rm --no-deps \\
    -v "$(pwd)/src:/app/src" \\
    -v "$(pwd)/scripts:/app/scripts" \\
    -e PYTHONPATH=/app/src \\
    -e VISAOVIP_SEARCH_ACTION_ENABLED=true \\
    -e VISAOVIP_SEARCH_ACTION_ID= \\
    api python scripts/_smoke_visaovip_strategy_a.py
"""

from __future__ import annotations

# ruff: noqa: E402
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("smoke_vv_a")

QUERIES = [
    "asus tuf gaming b650m-e wifi",
    "samsung galaxy s25 ultra",
]


def main() -> int:
    from scout_api.modules.crawler.services.product_scrape_service import (
        get_shared_html_fetcher,
    )
    from scout_api.modules.matching.search_adapters.paraguay import (
        visaovip_action_strategy as vv_action,
    )
    from scout_api.modules.matching.store_search_service import StoreSearchService

    vv_action.reset_action_id_cache_for_tests()
    fetcher = get_shared_html_fetcher()
    svc = StoreSearchService(fetcher=fetcher)

    rc = 0
    for query in QUERIES:
        t0 = time.perf_counter()
        try:
            cands = svc.search("visaovip", query, limit=8)
            elapsed = (time.perf_counter() - t0) * 1000
            cached = vv_action.get_cached_action_id()
            print(
                f"OK query={query!r} candidates={len(cands)} "
                f"elapsed_ms={elapsed:.0f} action_id_prefix="
                f"{(cached or '')[:12]!r}"
            )
            for c in cands[:3]:
                print(f"  - {c.product_id} | {c.title[:80]!r}")
            if not cands and "s25" in query.casefold():
                # Live catalog may return valid products:[] for this slug;
                # Strategy A still exercised (see logs: strategy_a_no_results).
                print("NOTE: S25 → 0 candidates (NO_RESULTS válido da Server Action)")
                rc = max(rc, 0)
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"FAIL query={query!r} elapsed_ms={elapsed:.0f} err={exc!r}")
            rc = 1
            logger.exception("search failed")

    try:
        close = getattr(fetcher, "close", None) or getattr(
            getattr(fetcher, "_direct", None), "close", None
        )
        if callable(close):
            close()
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
