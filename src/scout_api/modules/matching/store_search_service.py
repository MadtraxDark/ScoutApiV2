"""Live store SERP discovery using existing HtmlFetcher + spider adapters."""

from __future__ import annotations

import logging

from scout_api.modules.crawler.core.exceptions import ParseError, RequestError
from scout_api.modules.crawler.models.search import SearchCandidate
from scout_api.modules.crawler.services.html_fetcher import HtmlFetcher
from scout_api.modules.crawler.services.product_scrape_service import (
    get_shared_html_fetcher,
)
from scout_api.modules.crawler.services.store_resolver import (
    resolve_spider_by_store_key,
)
from scout_api.modules.crawler.spiders.base import BaseStoreSpider

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

        # Prefer candidates with distinct URLs, capped.
        seen: set[str] = set()
        selected: list[SearchCandidate] = []
        for candidate in candidates:
            key = candidate.url.strip()
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
