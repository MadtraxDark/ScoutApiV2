"""Live store SERP discovery using existing HtmlFetcher + spider adapters."""

from __future__ import annotations

import logging

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.models.search import SearchCandidate
from scout_api.modules.crawler.services.amazon_http_first_fetcher import (
    is_amazon_store_url,
)
from scout_api.modules.crawler.services.html_fetcher import (
    HtmlFetcher,
    is_amazon_robot_check,
    is_auth_wall_page,
    is_challenge_page,
)
from scout_api.modules.crawler.services.product_scrape_service import (
    get_shared_html_fetcher,
)
from scout_api.modules.crawler.services.store_resolver import (
    resolve_spider_by_store_key,
)
from scout_api.modules.crawler.spiders.base import BaseStoreSpider
from scout_api.modules.matching.identity import (
    enrich_candidate_title,
    rank_candidates_for_query,
)

logger = logging.getLogger(__name__)


class StoreSearchService:
    """Fetch and parse store search pages for product matching candidates."""

    def __init__(self, fetcher: HtmlFetcher | None = None) -> None:
        self._fetcher = fetcher or get_shared_html_fetcher()

    def search(
        self,
        store_key: str,
        query: str,
        *,
        limit: int = 5,
    ) -> list[SearchCandidate]:
        spider = resolve_spider_by_store_key(store_key)
        if not getattr(spider, "supports_search", False):
            raise RequestError(
                f"Busca não suportada para a loja {store_key}",
                code="SEARCH_UNSUPPORTED",
                url=None,
            )
        search_url = spider.build_search_url(query)
        fetch_url = spider.prepare_fetch_url(search_url)
        response = self._fetcher.fetch(fetch_url)
        text = response.text or ""
        page_url = str(response.url or search_url)
        # Challenge / robot / auth on SERP must never become silent NO_MATCH.
        if is_challenge_page(text) or is_amazon_robot_check(text):
            raise RequestError(
                "Busca bloqueada por challenge/CAPTCHA na loja",
                code="UPSTREAM_BLOCKED",
                url=page_url,
            )
        if is_auth_wall_page(text, url=page_url):
            raise RequestError(
                "Busca bloqueada por parede de autenticação na loja",
                code="AUTH_REQUIRED",
                url=page_url,
            )
        try:
            candidates = spider.parse_search_results(response)
        except NotImplementedError as exc:
            raise RequestError(
                str(exc),
                code="SEARCH_UNSUPPORTED",
                url=search_url,
            ) from exc
        except Exception as exc:
            logger.exception(
                "search_parse_failed",
                extra={"store": store_key, "url": search_url},
            )
            raise ParseError(
                f"Falha ao interpretar resultados de busca: {exc}"
            ) from exc

        # Amazon incomplete /s shell (no cards) after fetch escalation → blocked.
        if (
            not candidates
            and is_amazon_store_url(page_url)
            and "/s" in (page_url.split("?", 1)[0])
        ):
            # Distinguish genuine zero hits (message present) from empty shells.
            folded = text.casefold()
            genuine_empty = any(
                marker in folded
                for marker in (
                    "nenhum resultado",
                    "não encontramos",
                    "nao encontramos",
                    "no results for",
                    "did not match any products",
                    "0 results for",
                )
            )
            if not genuine_empty and "data-asin" not in folded:
                raise RequestError(
                    "SERP Amazon incompleta ou bloqueada (sem resultados parseáveis)",
                    code="UPSTREAM_BLOCKED",
                    url=page_url,
                )

        # Re-rank by query relevance before capping — retailers often promote
        # sibling SKUs above the exact manufacturer PN / series hit.
        # Fill empty SERP titles from URL slugs (Magalu/AliExpress static HTML).
        enriched = [enrich_candidate_title(c) for c in candidates]
        ranked = rank_candidates_for_query(list(enriched), query)

        # Prefer candidates with distinct URLs, capped.
        # Amazon: dedupe by market-scoped ASIN when present.
        seen: set[str] = set()
        selected: list[SearchCandidate] = []
        for candidate in ranked:
            asin = None
            if isinstance(candidate.metadata, dict):
                asin = candidate.metadata.get("asin") or candidate.product_id
            key = (
                f"{store_key}:{str(asin).upper()}"
                if asin and is_amazon_store_url(candidate.url)
                else candidate.url.strip()
            )
            if not key or key in seen:
                continue
            seen.add(key)
            selected.append(candidate)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def is_search_supported(store_key: str) -> bool:
        try:
            spider: BaseStoreSpider = resolve_spider_by_store_key(store_key)
        except RequestError:
            return False
        return bool(getattr(spider, "supports_search", False))
