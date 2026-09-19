"""Call POST /match once per search-capable store; aggregate results."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

REF = (
    "https://visaovip.com/prod/placas-de-video-nvidia/"
    "placa-de-video-msi-shadow-3x-oc-12gb-geforce-rtx5070-gddr7-912-v532-232/55359/"
)
STORES = [
    "kabum",
    "magazineluiza",
    "shopee",
    "amazon_br",
    "amazon_us",
    "bestbuy",
    "nissei",
    "shoppingchina",
]
OUT = Path("data/match_rtx5070_by_store.json")
BASE = "http://127.0.0.1:8000/match"


def post_match(store: str) -> dict:
    body = json.dumps(
        {
            "reference_url": REF,
            "stores": [store],
            "persist": False,
            "include_review": True,
            "max_candidates_per_store": 5,
        }
    ).encode()
    req = urllib.request.Request(
        BASE,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode())


def summarize(store: str, data: dict, secs: float) -> dict:
    return {
        "store": store,
        "secs": round(secs, 1),
        "matches": [
            {
                "decision": h.get("decision"),
                "confidence": h.get("confidence"),
                "title": ((h.get("product") or {}).get("title") or "")[:120],
                "price": (h.get("product") or {}).get("price"),
                "currency": (h.get("product") or {}).get("currency"),
                "brand": (h.get("product") or {}).get("brand"),
                "model": (h.get("product") or {}).get("model"),
                "sku": (h.get("product") or {}).get("sku"),
                "url": (h.get("product") or {}).get("url"),
                "reasons": [r.get("code") for r in (h.get("reasons") or [])],
            }
            for h in (data.get("matches") or [])
        ],
        "unmatched": data.get("unmatched_stores"),
        "errors": [
            {
                "store": e.get("store"),
                "code": e.get("code"),
                "message": (e.get("message") or "")[:180],
            }
            for e in (data.get("errors") or [])
        ],
        "reference_title": ((data.get("reference") or {}).get("title")),
        "reference_price": ((data.get("reference") or {}).get("price")),
    }


def main() -> None:
    rows: list[dict] = []
    for store in STORES:
        print(f"MATCH {store}", flush=True)
        t0 = time.time()
        try:
            data = post_match(store)
            row = summarize(store, data, time.time() - t0)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            row = {
                "store": store,
                "secs": round(time.time() - t0, 1),
                "http_error": exc.code,
                "detail": detail,
            }
        except Exception as exc:  # noqa: BLE001
            row = {
                "store": store,
                "secs": round(time.time() - t0, 1),
                "fatal": type(exc).__name__,
                "msg": str(exc)[:250],
            }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(2)

    payload = {"reference_url": REF, "results": rows}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT, flush=True)


if __name__ == "__main__":
    main()
