"""Live store SERP discovery via StoreSearchAdapter + shared HtmlFetcher."""

from __future__ import annotations

import logging

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
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
from scout_api.modules.matching.identity import (
    enrich_candidate_title,
    rank_candidates_for_query,
)
from scout_api.modules.matching.search_adapters.registry import (
    resolve_search_adapter,
    search_adapter_available,
)
from scout_api.modules.matching.search_candidate import SearchCandidate

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
        adapter = resolve_search_adapter(store_key)
        request = adapter.build_search_request(query)
        fetch_url = request.url
        logger.info(
            "store_search_fetch",
            extra={
                "store": store_key,
                "capability": "search",
                "operation": "fetch_serp",
                "prefer_browser": request.prefer_browser,
                "method": request.method,
                "url": fetch_url,
            },
        )
        # Shared HtmlFetcher stack; prefer_browser is an adapter policy signal
        # (logged / isolatable from PDP). Camoufox already covers SERP stores
        # that need hydration — no second browser pool.
        response = self._fetcher.fetch(fetch_url)
        text = response.text or ""
        page_url = str(response.url or fetch_url)
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
            candidates = adapter.parse_candidates(response)
        except NotImplementedError as exc:
            raise RequestError(
                str(exc),
                code="SEARCH_UNSUPPORTED",
                url=fetch_url,
            ) from exc
        except Exception as exc:
            logger.exception(
                "search_parse_failed",
                extra={
                    "store": store_key,
                    "capability": "search",
                    "url": fetch_url,
                },
            )
            raise ParseError(
                f"Falha ao interpretar resultados de busca: {exc}"
            ) from exc

        if not candidates:
            classification = adapter.classify_empty_result(response)
            if classification == "incomplete":
                raise RequestError(
                    "SERP incompleta ou bloqueada (sem resultados parseáveis)",
                    code="UPSTREAM_BLOCKED",
                    url=page_url,
                )

        enriched = [enrich_candidate_title(c) for c in candidates]
        ranked = rank_candidates_for_query(list(enriched), query)

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
        return search_adapter_available(store_key)
