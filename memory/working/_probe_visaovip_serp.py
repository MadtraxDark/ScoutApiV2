"""Probe Visão VIP SERP via shared HtmlFetcher (Camoufox)."""

from __future__ import annotations

import re

from scout_api.modules.crawler.services.product_scrape_service import (
    get_shared_html_fetcher,
)

URL = "https://www.visaovip.com/busca/termo/ASUS-TUF-Gaming-B650M-E-WIFI/"
_PROD = re.compile(r"/prod/(?:[^/\s\"'<>]+/)+(\d+)/?", re.I)


def main() -> None:
    print("fetching", URL)
    fetcher = get_shared_html_fetcher()
    resp = fetcher.fetch(URL)
    text = resp.text or ""
    print("len", len(text), "final_url", resp.url)
    print("has_41749", "41749" in text)
    paths = sorted({m.group(0) for m in _PROD.finditer(text)})
    print("product_paths", paths[:15])
    print("count", len(paths))


if __name__ == "__main__":
    main()
