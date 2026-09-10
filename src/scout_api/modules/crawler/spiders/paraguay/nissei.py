from ..base import BaseStoreSpider


class NisseiSpider(BaseStoreSpider):
    name = "nissei"
    store, country, currency = "nissei", "PY", "PYG"
    allowed_domains = ["nissei.com"]
    start_urls: list[str] = []
