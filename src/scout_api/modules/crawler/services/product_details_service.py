from scrapy.http import HtmlResponse

from ..core.scrape_guard import ScrapeGuard
from ..models.product import ProductDetails
from ..spiders.base import BaseStoreSpider
from .html_fetcher import HtmlFetcher
from .product_scrape_service import get_shared_html_fetcher, get_shared_scrape_guard
from .store_resolver import resolve_store_spider


class ProductDetailsService:
    """Fetch a product URL and extract only catalog/identity details."""

    def __init__(
        self,
        fetcher: HtmlFetcher | None = None,
        guard: ScrapeGuard | None = None,
    ) -> None:
        self._fetcher = fetcher or get_shared_html_fetcher()
        self._guard = guard or get_shared_scrape_guard()

    def scrape_details(self, url: str) -> ProductDetails:
        spider = self._spider_for(url)
        self._guard.acquire_for_live_fetch(url)
        response = self._fetch(url)
        return spider.extract_details(response)

    def _fetch(self, url: str) -> HtmlResponse:
        return self._fetcher.fetch(url)

    @staticmethod
    def _spider_for(url: str) -> BaseStoreSpider:
        return resolve_store_spider(url)
