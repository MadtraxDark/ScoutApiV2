from urllib.parse import urlparse

from ..core.exceptions import RequestError
from ..spiders.base import BaseStoreSpider
from ..spiders.brazil.magazineluiza import MagazineLuizaSpider
from ..spiders.paraguay.nissei import NisseiSpider


def resolve_store_spider(url: str) -> BaseStoreSpider:
    """Map a product URL hostname to the store spider adapter."""
    hostname = (urlparse(url).hostname or "").lower()
    if hostname == "magazineluiza.com.br" or hostname.endswith(".magazineluiza.com.br"):
        return MagazineLuizaSpider()
    if hostname == "nissei.com" or hostname.endswith(".nissei.com"):
        return NisseiSpider()
    raise RequestError(
        "Nenhum spider disponível para este domínio",
        code="UNSUPPORTED_STORE",
        url=url,
    )
