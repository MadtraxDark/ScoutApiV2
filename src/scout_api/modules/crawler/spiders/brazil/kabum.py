from ..base import BaseStoreSpider


class KabumSpider(BaseStoreSpider):
    name = "kabum"
    store, country, currency = "kabum", "BR", "BRL"
    allowed_domains = ["kabum.com.br"]
    start_urls: list[str] = []
