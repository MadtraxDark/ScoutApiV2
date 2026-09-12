"""Measure Shopee fetch cost (bytes / requests / warm-up / get_pc timing).

Baseline probe for cost-aware proxy work. Uses one product URL and does not
print proxy credentials.

Example:
    .\\.venv\\Scripts\\python.exe scripts\\measure_shopee_fetch_cost.py
    .\\.venv\\Scripts\\python.exe scripts\\measure_shopee_fetch_cost.py \\
        --block-resources
    .\\.venv\\Scripts\\python.exe scripts\\measure_shopee_fetch_cost.py \\
        --no-warmup --early-stop
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scout_api.core.config import get_settings  # noqa: E402
from scout_api.modules.crawler.services.html_fetcher import (  # noqa: E402
    CamoufoxHtmlFetcher,
    apply_shopee_br_proxy_targeting,
    is_shopee_get_pc_url,
    looks_like_shopee_pdp,
    proxy_settings_from_url,
    shopee_ids_from_url,
    warmup_url_for,
    wrap_shopee_pdp_json,
)

DEFAULT_URL = (
    "https://shopee.com.br/Kingston-HyperX-Fury-DDR4-PC-RAM-4-Gb-8-16-DDR4-"
    "2133-2400-2666-3200-Mhz-Mem%C3%B3ria-De-Mesa-i.341936748.29277977480"
)
HOST_PROFILE = ROOT / "data" / "camoufox-profiles" / "default"
BLOCKED_TYPES = ("image", "media", "font")


def _estimate_bytes(response: Any) -> int:
    try:
        headers = response.headers
        cl = headers.get("content-length") if headers else None
        if cl is not None:
            return max(0, int(cl))
    except Exception:
        pass
    try:
        body = response.body()
        if body is not None:
            return len(body)
    except Exception:
        pass
    return 0


def measure(
    *,
    url: str,
    warmup: bool,
    early_stop: bool,
    block_resources: bool,
    profile_dir: Path,
    proxy_url: str | None,
    timeout_ms: int,
) -> dict[str, Any]:
    from camoufox.addons import DefaultAddons
    from camoufox.sync_api import Camoufox

    launch: dict[str, Any] = {
        "headless": True,
        "humanize": True,
        "os": "windows",
        "geoip": True,
        "persistent_context": True,
        "user_data_dir": str(profile_dir),
        "locale": "pt-BR",
        "exclude_addons": [DefaultAddons.UBO],
        "disable_coop": True,
        "i_know_what_im_doing": True,
    }
    if proxy_url:
        targeted = apply_shopee_br_proxy_targeting(proxy_url, url)
        launch["proxy"] = proxy_settings_from_url(targeted)
        launch["geoip"] = False

    requests_by_type: Counter[str] = Counter()
    requests_by_host: Counter[str] = Counter()
    bytes_by_type: Counter[str] = Counter()
    total_bytes = 0
    request_count = 0
    image_requests = 0
    get_pc_at_ms: float | None = None
    get_pc_captured = False
    navigations: list[str] = []
    captured: dict[str, str] = {}
    post_get_pc_bytes = 0
    post_get_pc_requests = 0
    t0 = time.perf_counter()

    ids = shopee_ids_from_url(url)
    wanted_shop = ids[0] if ids else None
    wanted_item = ids[1] if ids else None

    with Camoufox(**launch) as browser:  # type: ignore[no-untyped-call]
        page = browser.new_page() if hasattr(browser, "new_page") else browser.pages[0]

        if block_resources:

            def _route(route: Any, request: Any) -> None:
                if request.resource_type in BLOCKED_TYPES:
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", _route)

        def on_request(request: Any) -> None:
            nonlocal request_count, image_requests
            rtype = str(getattr(request, "resource_type", "unknown") or "unknown")
            host = urlparse(str(request.url)).hostname or ""
            requests_by_type[rtype] += 1
            requests_by_host[host] += 1
            request_count += 1
            if rtype == "image":
                image_requests += 1
            if get_pc_captured:
                nonlocal post_get_pc_requests
                post_get_pc_requests += 1

        def on_response(response: Any) -> None:
            nonlocal total_bytes, post_get_pc_bytes, get_pc_at_ms, get_pc_captured
            rtype = str(
                getattr(getattr(response, "request", None), "resource_type", "unknown")
                or "unknown"
            )
            size = _estimate_bytes(response)
            total_bytes += size
            bytes_by_type[rtype] += size
            if get_pc_captured:
                post_get_pc_bytes += size

            response_url = str(getattr(response, "url", "") or "")
            if get_pc_captured or not is_shopee_get_pc_url(response_url):
                return
            if wanted_shop and wanted_shop not in response_url:
                return
            if wanted_item and wanted_item not in response_url:
                return
            try:
                status = int(getattr(response, "status", 0) or 0)
            except (TypeError, ValueError):
                status = 0
            if status and status >= 400:
                return
            try:
                raw = response.text()
            except Exception:
                return
            if not isinstance(raw, str) or not raw.strip().startswith("{"):
                return
            if not looks_like_shopee_pdp(raw):
                return
            captured["body"] = raw
            get_pc_captured = True
            get_pc_at_ms = (time.perf_counter() - t0) * 1000

        page.on("request", on_request)
        page.on("response", on_response)

        if warmup:
            warm = warmup_url_for(url)
            if warm:
                navigations.append(warm)
                page.goto(warm, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state(
                        "networkidle", timeout=min(20_000, timeout_ms)
                    )
                except Exception:
                    pass
                page.wait_for_timeout(3_000)

        navigations.append(url)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

        if early_stop:
            deadline = time.perf_counter() + (timeout_ms / 1000)
            while not get_pc_captured and time.perf_counter() < deadline:
                page.wait_for_timeout(200)
            # close ASAP after capture
        else:
            try:
                page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
            except Exception:
                pass
            # mimic settle loop briefly
            for _ in range(3):
                if get_pc_captured:
                    break
                page.wait_for_timeout(1000)

        html = (
            wrap_shopee_pdp_json(captured["body"])
            if captured.get("body")
            else page.content()
        )
        duration_ms = (time.perf_counter() - t0) * 1000
        try:
            page.close()
        except Exception:
            pass

    return {
        "url": url,
        "proxy_used": bool(proxy_url),
        "warmup_used": warmup,
        "early_stop": early_stop,
        "block_resources": block_resources,
        "blocked_types": list(BLOCKED_TYPES) if block_resources else [],
        "navigations": navigations,
        "navigation_count": len(navigations),
        "get_pc_captured": get_pc_captured,
        "get_pc_at_ms": round(get_pc_at_ms, 1) if get_pc_at_ms is not None else None,
        "network_request_count": request_count,
        "image_request_count": image_requests,
        "requests_by_resource_type": dict(requests_by_type),
        "top_hosts": requests_by_host.most_common(15),
        "estimated_transferred_bytes": total_bytes,
        "bytes_by_resource_type": dict(bytes_by_type),
        "post_get_pc_requests": post_get_pc_requests,
        "post_get_pc_bytes": post_get_pc_bytes,
        "duration_ms": round(duration_ms, 1),
        "response_html_bytes": len(html.encode("utf-8")),
        "result": "success" if get_pc_captured else "no_get_pc",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("--early-stop", action="store_true")
    parser.add_argument("--block-resources", action="store_true")
    parser.add_argument("--label", default="baseline")
    parser.add_argument(
        "--out",
        default=str(ROOT / "data" / "fetch-cost-metrics"),
        help="Directory for JSON reports",
    )
    args = parser.parse_args()

    settings = get_settings()
    profile = HOST_PROFILE
    if settings.camoufox_user_data_dir:
        configured = Path(settings.camoufox_user_data_dir)
        if "camoufox-profiles" in configured.as_posix():
            profile = HOST_PROFILE
        else:
            profile = configured
    profile.mkdir(parents=True, exist_ok=True)

    print("Stopping Docker API briefly to avoid profile lock...")
    import subprocess

    subprocess.run(
        ["docker", "compose", "stop", "api"],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
    )

    report = measure(
        url=args.url,
        warmup=not args.no_warmup,
        early_stop=args.early_stop,
        block_resources=args.block_resources,
        profile_dir=profile,
        proxy_url=settings.camoufox_proxy_url,
        timeout_ms=settings.camoufox_timeout_ms,
    )
    report["label"] = args.label
    report["proxy_policy_assumed"] = "global_if_configured"

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"{args.label}-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"\nWrote {out_path}")

    subprocess.run(
        ["docker", "compose", "start", "api"],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
    )
    return 0 if report["get_pc_captured"] else 2


if __name__ == "__main__":
    # Silence unused import lint for CamoufoxHtmlFetcher (documents parity).
    _ = CamoufoxHtmlFetcher
    raise SystemExit(main())
