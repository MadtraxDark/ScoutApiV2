from ..base import BaseStoreSpider


class BestBuySpider(BaseStoreSpider):
    name = "bestbuy"
    store, country, currency = "bestbuy", "US", "USD"
    allowed_domains = ["bestbuy.com"]
    start_urls: list[str] = []
