from scrapy.http import HtmlResponse

from ..core.scrape_guard import ScrapeGuard
from ..models.product import ProductDetails, candidates_from_urls
from ..spiders.base import BaseStoreSpider
from .html_fetcher import HtmlFetcher
from .product_scrape_service import (
    _proxy_used,
    get_shared_html_fetcher,
    get_shared_scrape_guard,
)
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

    def scrape_details(
        self, url: str, *, include_images: bool = False
    ) -> ProductDetails:
        spider = self._spider_for(url)
        self._guard.acquire_for_live_fetch(url)
        response = self._fetch(spider.prepare_fetch_url(url))
        details = spider.extract_details(response)
        proxy_used = _proxy_used(response)
        allow_images = include_images and spider.supports_images and not proxy_used
        if allow_images:
            urls = spider.extract_images(response)
            details = details.model_copy(
                update={
                    "images": urls,
                    "image_candidates": candidates_from_urls(urls),
                }
            )
        elif include_images:
            reason = "proxy-cost-mode" if proxy_used else "store-cost-policy"
            details = details.model_copy(
                update={
                    "images": [],
                    "image_candidates": [],
                    "metadata": {
                        **details.metadata,
                        "images_omitted": reason,
                    },
                }
            )
        return details

    def _fetch(self, url: str) -> HtmlResponse:
        return self._fetcher.fetch(url)

    @staticmethod
    def _spider_for(url: str) -> BaseStoreSpider:
        return resolve_store_spider(url)
