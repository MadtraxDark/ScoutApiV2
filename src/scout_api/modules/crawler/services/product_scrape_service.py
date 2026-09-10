from urllib.parse import urlparse

from scrapy.http import HtmlResponse

from ....core.config import get_settings
from ..core.exceptions import RequestError
from ..models.product import ProductPriceItem
from ..spiders.base import BaseStoreSpider
from ..spiders.brazil.magazineluiza import MagazineLuizaSpider
from ..spiders.paraguay.nissei import NisseiSpider
from .html_fetcher import HtmlFetcher, build_html_fetcher


class ProductScrapeService:
    """Fetch one product URL and normalize it through the matching spider."""

    def __init__(self, fetcher: HtmlFetcher | None = None) -> None:
        settings = get_settings()
        self._fetcher = fetcher or build_html_fetcher(
            camoufox_enabled=settings.camoufox_enabled,
            user_agent=settings.scraper_user_agent,
            urllib_timeout=settings.scraper_http_timeout,
            camoufox_headless=settings.camoufox_headless,
            camoufox_humanize=settings.camoufox_humanize,
            camoufox_timeout_ms=settings.camoufox_timeout_ms,
            camoufox_settle_ms=settings.camoufox_settle_ms,
            camoufox_max_settle_attempts=settings.camoufox_max_settle_attempts,
        )

    def scrape(self, url: str) -> ProductPriceItem:
        spider = self._spider_for(url)
        response = self._fetch(url)
        return spider.parse_product(response)

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
