from scrapy.http import HtmlResponse

from ..core.scrape_guard import ScrapeGuard
from ..models.product import ProductOffer, product_offer_from_price_item
from ..spiders.base import BaseStoreSpider
from .html_fetcher import HtmlFetcher
from .product_scrape_service import get_shared_html_fetcher, get_shared_scrape_guard
from .store_resolver import resolve_store_spider


class OfferScrapeService:
    """Fetch a product URL and extract only the commercial offer snapshot."""

    def __init__(
        self,
        fetcher: HtmlFetcher | None = None,
        guard: ScrapeGuard | None = None,
    ) -> None:
        self._fetcher = fetcher or get_shared_html_fetcher()
        self._guard = guard or get_shared_scrape_guard()

    def scrape_offer(self, url: str) -> ProductOffer:
        cached = self._guard.get_cached(url)
        if cached is not None:
            return product_offer_from_price_item(cached)

        spider = self._spider_for(url)
        self._guard.acquire_for_live_fetch(url)
        response = self._fetch(url)
        return spider.extract_offer(response)

    def _fetch(self, url: str) -> HtmlResponse:
        return self._fetcher.fetch(url)

    @staticmethod
    def _spider_for(url: str) -> BaseStoreSpider:
        return resolve_store_spider(url)
