from functools import lru_cache
from urllib.parse import urlparse

from scrapy.http import HtmlResponse

from ....core.config import get_settings
from ..core.exceptions import RequestError
from ..core.scrape_guard import ScrapeGuard
from ..models.product import ProductPriceItem
from ..spiders.base import BaseStoreSpider
from ..spiders.brazil.magazineluiza import MagazineLuizaSpider
from ..spiders.paraguay.nissei import NisseiSpider
from .html_fetcher import HtmlFetcher, build_html_fetcher


@lru_cache
def get_shared_html_fetcher() -> HtmlFetcher:
    settings = get_settings()
    return build_html_fetcher(
        camoufox_enabled=settings.camoufox_enabled,
        user_agent=settings.scraper_user_agent,
        urllib_timeout=settings.scraper_http_timeout,
        camoufox_headless=settings.camoufox_headless,
        camoufox_humanize=settings.camoufox_humanize,
        camoufox_timeout_ms=settings.camoufox_timeout_ms,
        camoufox_settle_ms=settings.camoufox_settle_ms,
        camoufox_max_settle_attempts=settings.camoufox_max_settle_attempts,
        camoufox_proxy_url=settings.camoufox_proxy_url,
        camoufox_user_data_dir=settings.camoufox_user_data_dir,
        camoufox_disable_coop=settings.camoufox_disable_coop,
        camoufox_warmup_origin=settings.camoufox_warmup_origin,
    )


@lru_cache
def get_shared_scrape_guard() -> ScrapeGuard:
    settings = get_settings()
    return ScrapeGuard(
        url_cooldown_seconds=settings.scrape_url_cooldown_seconds,
        domain_min_interval_seconds=settings.scrape_domain_min_interval_seconds,
        result_cache_ttl_seconds=settings.scrape_result_cache_ttl_seconds,
    )


class ProductScrapeService:
    """Fetch one product URL and normalize it through the matching spider."""

    def __init__(
        self,
        fetcher: HtmlFetcher | None = None,
        guard: ScrapeGuard | None = None,
    ) -> None:
        self._fetcher = fetcher or get_shared_html_fetcher()
        self._guard = guard or get_shared_scrape_guard()

    def scrape(self, url: str) -> ProductPriceItem:
        cached = self._guard.get_cached(url)
        if cached is not None:
            return cached

        spider = self._spider_for(url)
        self._guard.acquire_for_live_fetch(url)
        response = self._fetch(url)
        item = spider.parse_product(response)
        self._guard.store_success(url, item)
        return item

    def _fetch(self, url: str) -> HtmlResponse:
        return self._fetcher.fetch(url)

    @staticmethod
    def _spider_for(url: str) -> BaseStoreSpider:
        hostname = (urlparse(url).hostname or "").lower()
        if hostname == "magazineluiza.com.br" or hostname.endswith(
            ".magazineluiza.com.br"
        ):
            return MagazineLuizaSpider()
        if hostname == "nissei.com" or hostname.endswith(".nissei.com"):
            return NisseiSpider()
        raise RequestError(
            "Nenhum spider disponível para este domínio",
            code="UNSUPPORTED_STORE",
            url=url,
        )
