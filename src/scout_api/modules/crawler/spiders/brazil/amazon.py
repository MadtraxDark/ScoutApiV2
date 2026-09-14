"""Amazon Brazil (amazon.com.br) store adapter."""

from urllib.parse import quote_plus

from scrapy.http import Response

from ...models.product import ProductDetails, ProductOffer
from ...models.search import SearchCandidate
from ..amazon.marketplace import AMAZON_BR
from ..amazon.parsing import (
    extract_amazon_details,
    extract_amazon_images,
    extract_amazon_offer,
    prepare_amazon_fetch_url,
)
from ..amazon.search import parse_amazon_search_results
from ..base import BaseStoreSpider


class AmazonBrazilSpider(BaseStoreSpider):
    """Amazon.com.br — independent BR marketplace offers (BRL)."""

    name = "amazon_br"
    store, country, currency = "amazon", "BR", "BRL"
    supports_search = True
    allowed_domains = ["amazon.com.br", "www.amazon.com.br"]
    start_urls: list[str] = []

    def prepare_fetch_url(self, url: str) -> str:
        return prepare_amazon_fetch_url(url, AMAZON_BR.host)

    def build_search_url(self, query: str) -> str:
        return f"https://www.amazon.com.br/s?k={quote_plus(query.strip())}"

    def parse_search_results(self, response: Response) -> list[SearchCandidate]:
        return parse_amazon_search_results(
            response,
            host=AMAZON_BR.host,
            source="amazon-br-search",
        )

    def extract_offer(self, response: Response) -> ProductOffer:
        return extract_amazon_offer(self, response, AMAZON_BR)

    def extract_details(self, response: Response) -> ProductDetails:
        return extract_amazon_details(self, response, AMAZON_BR)

    def extract_images(self, response: Response) -> list[str]:
        return extract_amazon_images(response)
