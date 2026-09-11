from functools import lru_cache

from scrapy.http import HtmlResponse

from ....core.config import get_settings
from ..core.scrape_guard import ScrapeGuard
from ..models.product import ProductPriceItem, compose_product_price_item
from ..spiders.base import BaseStoreSpider
from .html_fetcher import HtmlFetcher, build_html_fetcher
from .store_resolver import resolve_store_spider


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
    """Orchestrate a full product scrape from offer + details extractors."""

    def __init__(
        self,
        fetcher: HtmlFetcher | None = None,
        guard: ScrapeGuard | None = None,
    ) -> None:
        self._fetcher = fetcher or get_shared_html_fetcher()
        self._guard = guard or get_shared_scrape_guard()

    def scrape(self, url: str, *, include_images: bool = False) -> ProductPriceItem:
        cached = self._guard.get_cached(url)
        if cached is not None:
            if not include_images and cached.images:
                return cached.model_copy(update={"images": []})
            if include_images and cached.images:
                return cached
            if not include_images:
                return cached

        spider = self._spider_for(url)
        fetch_url = spider.prepare_fetch_url(url)
        self._guard.acquire_for_live_fetch(url)
        response = self._fetch(fetch_url)
        offer = spider.extract_offer(response)
        details = spider.extract_details(response)
        if include_images:
            details = details.model_copy(
                update={"images": spider.extract_images(response)}
            )
        item = compose_product_price_item(offer, details)
        self._guard.store_success(url, item)
        return item

    def _fetch(self, url: str) -> HtmlResponse:
        return self._fetcher.fetch(url)

    @staticmethod
    def _spider_for(url: str) -> BaseStoreSpider:
        return resolve_store_spider(url)
