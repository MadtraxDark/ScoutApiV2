"""Shared Amazon SERP parsing for regional spiders."""

from __future__ import annotations

from urllib.parse import urljoin

from scrapy.http import Response

from ...core.fingerprints import canonicalize_url
from ...models.search import SearchCandidate


def parse_amazon_search_results(
    response: Response,
    *,
    host: str,
    source: str,
    limit: int = 10,
) -> list[SearchCandidate]:
    """Parse classic Amazon ``s-search-result`` cards into PDP candidates."""
    candidates: list[SearchCandidate] = []
    seen: set[str] = set()
    for card in response.css(
        "div[data-component-type='s-search-result'], div.s-result-item[data-asin]"
    ):
        asin = (card.attrib.get("data-asin") or "").strip()
        if not asin or len(asin) != 10:
            continue
        href = card.css(
            "h2 a::attr(href), a.a-link-normal.s-no-outline::attr(href)"
        ).get()
        if href:
            absolute = urljoin(response.url, href.strip())
        else:
            absolute = f"https://www.{host}/dp/{asin}"
        canonical = canonicalize_url(absolute)
        if canonical in seen:
            continue
        seen.add(canonical)
        title = card.css("h2 a span::text, h2 span::text").get()
        candidates.append(
            SearchCandidate(
                url=absolute,
                title=title.strip() if title else None,
                product_id=asin,
                metadata={"source": source, "asin": asin},
            )
        )
        if len(candidates) >= limit:
            break
    return candidates
