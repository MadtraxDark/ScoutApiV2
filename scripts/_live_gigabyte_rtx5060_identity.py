"""Live identity-only Product Search + Match for Gigabyte GeForce RTX 5060.

Starts from product identity only — no known KaBuM / Mercado Livre / AliExpress
URLs, IDs, sellers, or prices are fed into Search. Ground-truth stores from the
human screenshot are used only for reporting / investigation classification.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.services.product_scrape_service import (
    ProductScrapeService,
)
from scout_api.modules.crawler.stores import STORE_CONFIGS
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.identity import (
    build_search_queries,
    identity_from_price_item,
    identity_reference_item,
)
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.store_search_order import order_stores_for_match
from scout_api.modules.matching.store_search_service import StoreSearchService

SOURCE_TITLE = "Placa de Vídeo Gigabyte GeForce RTX 5060"
# Human ground truth only — never passed to Search/Match as hints.
GROUND_TRUTH_STORES = frozenset({"kabum", "mercadolivre", "aliexpress"})


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    return str(obj)


def _classify_failure(
    *,
    store: str,
    matched: bool,
    candidates_total: int,
    scrape_ok: int,
    scrape_fail: int,
    best_rejected: bool,
    error_code: str | None,
) -> str:
    if matched:
        return "MATCH"
    if error_code in {
        "UPSTREAM_BLOCKED",
        "RATE_LIMITED",
        "CHALLENGE",
        "AUTH_WALL",
        "NET_RESET",
        "TIMEOUT",
    }:
        return "BLOCKED"
    if error_code in {"SEARCH_UNSUPPORTED", "PARSE_ERROR"} or (
        error_code and error_code not in {"NO_MATCH"}
    ):
        if error_code == "SEARCH_UNSUPPORTED":
            return "ERROR"
        if candidates_total == 0 and error_code:
            return "ERROR"
        if scrape_fail and not scrape_ok:
            return "SCRAPE_FAILURE"
        return "ERROR"
    if candidates_total == 0:
        return "SEARCH_FAILURE" if store in GROUND_TRUTH_STORES else "NO_MATCH"
    if scrape_ok == 0 and scrape_fail > 0:
        return "SCRAPE_FAILURE"
    if best_rejected:
        return "MATCH_FAILURE"
    return "NO_MATCH"


def main() -> int:
    out_dir = ROOT / "data" / "live-match-reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"gigabyte_rtx5060_identity_{stamp}.json"

    reference = identity_reference_item(SOURCE_TITLE, category="gpu")
    ref_identity = identity_from_price_item(reference)
    queries = build_search_queries(ref_identity)

    implemented = [k for k, cfg in STORE_CONFIGS.items() if cfg.implemented]
    ordered = order_stores_for_match(
        implemented,
        reference_store=reference.store,
        reference_has_gtin=False,
    )

    print("=== IDENTITY-ONLY LIVE MATCH ===", flush=True)
    print("title=", SOURCE_TITLE, flush=True)
    print(
        "identity=",
        {
            "brand": ref_identity.brand,
            "model": ref_identity.model,
            "variant_attrs": ref_identity.variant_attrs,
            "gtin": ref_identity.gtin,
            "mpn": ref_identity.mpn,
        },
        flush=True,
    )
    print("queries=", queries, flush=True)
    print("stores=", ordered, flush=True)

    search = StoreSearchService()
    engine = MatchingEngine()
    scrape = ProductScrapeService()
    matcher = ProductMatchService(scrape_service=scrape, search_service=search)

    # --- Step 3: candidate retrieval probe (Search layer only) ---
    retrieval: dict[str, Any] = {}
    for store in ordered:
        if not search.is_search_supported(store):
            retrieval[store] = {
                "supported": False,
                "status": "ERROR",
                "reason": "SEARCH_UNSUPPORTED",
            }
            continue
        store_rows: list[dict[str, Any]] = []
        used_query = None
        candidates_acc: list[Any] = []
        for query in queries[:3]:
            try:
                found = search.search(store, query, limit=5)
            except (RequestError, ParseError) as exc:
                store_rows.append(
                    {
                        "query": query,
                        "error": {
                            "type": type(exc).__name__,
                            "code": getattr(exc, "code", None),
                            "message": str(exc)[:400],
                        },
                    }
                )
                continue
            store_rows.append(
                {
                    "query": query,
                    "count": len(found),
                    "candidates": [
                        {
                            "title": (c.title or "")[:160],
                            "url": c.url,
                            "product_id": c.product_id,
                        }
                        for c in found
                    ],
                }
            )
            if found and used_query is None:
                used_query = query
                candidates_acc = found
                break
        retrieval[store] = {
            "supported": True,
            "probe_queries": store_rows,
            "winning_query": used_query,
            "candidate_count": len(candidates_acc),
        }
        print(
            f"retrieval {store}: query={used_query!r} n={len(candidates_acc)}",
            flush=True,
        )

    # --- Full Search + Match (identity-only) ---
    t0 = time.perf_counter()
    try:
        response = matcher.match_from_item(
            reference,
            stores=ordered,
            include_review=True,
            persist=False,
            include_images=False,
            max_candidates_per_store=5,
            clear_reference_price=True,
        )
        match_error = None
    except Exception as exc:  # noqa: BLE001 — live report
        response = None
        match_error = {
            "type": type(exc).__name__,
            "message": str(exc)[:800],
            "traceback": traceback.format_exc()[-2000:],
        }
        print("MATCH_FATAL", match_error["type"], match_error["message"], flush=True)
    elapsed = time.perf_counter() - t0
    print(f"match_elapsed_s={elapsed:.1f}", flush=True)

    per_store: dict[str, Any] = {}
    table_rows: list[dict[str, Any]] = []

    if response is not None:
        matched_stores = {m.store: m for m in response.matches}
        errors_by_store = {e.store: e for e in response.errors}
        unmatched = set(response.unmatched_stores)

        for store in ordered:
            hit = matched_stores.get(store)
            err = errors_by_store.get(store)
            probe = retrieval.get(store) or {}
            cand_n = int(probe.get("candidate_count") or 0)
            if hit is not None:
                status = "MATCH"
                reason = "; ".join(
                    f"{r.code}:{r.detail}" for r in (hit.reasons or [])[:4]
                )
                best = {
                    "title": hit.product.title,
                    "url": hit.product.url,
                    "product_id": hit.product.product_id,
                    "price": str(hit.product.price) if hit.product.price else None,
                    "seller": hit.product.seller,
                }
                score = str(hit.confidence)
                query = hit.search_query
                terminal = "MATCH"
            else:
                code = err.code if err else None
                msg = err.message if err else None
                # Offline score first retrieval candidate when present (diagnosis).
                best_rejected = False
                best = None
                score = None
                query = probe.get("winning_query")
                if cand_n and query:
                    try:
                        cands = search.search(store, str(query), limit=3)
                    except Exception:  # noqa: BLE001
                        cands = []
                    for cand in cands[:1]:
                        try:
                            product = scrape.scrape(cand.url, include_images=False)
                            sc = engine.score(
                                ref_identity, identity_from_price_item(product)
                            )
                            best = {
                                "title": product.title,
                                "url": product.url,
                                "product_id": product.product_id,
                                "decision": sc.decision,
                                "confidence": str(sc.confidence),
                                "reasons": [
                                    {"code": r.code, "detail": r.detail}
                                    for r in sc.reasons[:5]
                                ],
                            }
                            score = str(sc.confidence)
                            best_rejected = sc.decision == "reject"
                        except Exception as scrape_exc:  # noqa: BLE001
                            best = {
                                "url": cand.url,
                                "scrape_error": str(scrape_exc)[:300],
                            }
                failure = _classify_failure(
                    store=store,
                    matched=False,
                    candidates_total=cand_n,
                    scrape_ok=1 if best and "scrape_error" not in (best or {}) else 0,
                    scrape_fail=1 if best and "scrape_error" in (best or {}) else 0,
                    best_rejected=best_rejected,
                    error_code=code,
                )
                status = failure
                reason = msg or failure
                if store in unmatched and not code and cand_n == 0:
                    terminal = "NO_MATCH"
                elif hit is None and code:
                    terminal = "ERROR"
                else:
                    terminal = "NO_MATCH" if failure in {
                        "NO_MATCH",
                        "SEARCH_FAILURE",
                        "MATCH_FAILURE",
                        "NORMALIZATION_FAILURE",
                    } else "ERROR"
                if failure == "BLOCKED":
                    terminal = "ERROR"

            row = {
                "store": store,
                "query": query,
                "candidates": cand_n,
                "best_candidate": (best or {}).get("title") if best else None,
                "best_url": (best or {}).get("url") if best else None,
                "match_score": score,
                "status": status,
                "terminal": terminal,
                "reason": reason,
                "ground_truth": store in GROUND_TRUTH_STORES,
            }
            table_rows.append(row)
            per_store[store] = {
                **row,
                "best": best,
                "error": err.model_dump() if err else None,
                "retrieval": probe,
            }
            print(
                f"| {store} | {query} | {cand_n} | "
                f"{(best or {}).get('title', '')!s:.40} | {score} | "
                f"{status} | {str(reason)[:60]} |",
                flush=True,
            )

    report: dict[str, Any] = {
        "started_at": stamp,
        "mode": "identity_only",
        "source_title": SOURCE_TITLE,
        "identity": {
            "brand": ref_identity.brand,
            "model": ref_identity.model,
            "variant_attrs": dict(ref_identity.variant_attrs),
            "gtin": ref_identity.gtin,
            "mpn": ref_identity.mpn,
            "title_normalized": ref_identity.title_normalized,
        },
        "queries": queries,
        "stores_ordered": ordered,
        "ground_truth_stores": sorted(GROUND_TRUTH_STORES),
        "match_elapsed_seconds": round(elapsed, 2),
        "match_error": match_error,
        "retrieval": retrieval,
        "table": table_rows,
        "per_store": per_store,
        "matches": (
            [
                {
                    "store": m.store,
                    "decision": m.decision,
                    "confidence": str(m.confidence),
                    "search_query": m.search_query,
                    "url": m.product.url,
                    "product_id": m.product.product_id,
                    "title": m.product.title,
                    "price": str(m.product.price) if m.product.price else None,
                    "seller": m.product.seller,
                    "reasons": [
                        {"code": r.code, "detail": r.detail, "score": r.score}
                        for r in m.reasons
                    ],
                }
                for m in (response.matches if response else [])
            ]
        ),
        "unmatched_stores": list(response.unmatched_stores) if response else [],
        "errors": [e.model_dump() for e in response.errors] if response else [],
    }

    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(f"\nWrote {report_path}", flush=True)

    # Ground-truth summary
    for store in sorted(GROUND_TRUTH_STORES):
        row = next((r for r in table_rows if r["store"] == store), None)
        print(f"GROUND_TRUTH {store}: {row}", flush=True)

    ok = all(
        (next((r for r in table_rows if r["store"] == s), None) or {}).get("status")
        == "MATCH"
        for s in GROUND_TRUTH_STORES
    )
    return 0 if ok and match_error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
