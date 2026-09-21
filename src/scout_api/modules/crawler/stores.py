"""Central catalog: adding a store does not require changing crawler core."""

from dataclasses import dataclass
from typing import Literal

from .core.proxy_policy import ProxyPolicy

ImageFetchCost = Literal["low", "high", "unsupported"]


@dataclass(frozen=True)
class StoreConfig:
    key: str
    country: str
    currency: str
    domains: tuple[str, ...]
    implemented: bool = False
    proxy_policy: ProxyPolicy = ProxyPolicy.FALLBACK
    supports_images: bool = True
    # UX / cost hint for clients (PriceScout checkbox default). Never exposes
    # proxy URLs or bypass details.
    image_fetch_cost: ImageFetchCost = "low"

    @property
    def default_include_images(self) -> bool:
        """True when gallery extraction is cheap enough to opt-in by default."""
        return self.supports_images and self.image_fetch_cost == "low"


STORE_CONFIGS = {
    "kabum": StoreConfig("kabum", "BR", "BRL", ("kabum.com.br",), True),
    "magazineluiza": StoreConfig(
        "magazineluiza", "BR", "BRL", ("magazineluiza.com.br",), True
    ),
    "mercadolivre": StoreConfig(
        "mercadolivre",
        "BR",
        "BRL",
        ("mercadolivre.com.br", "produto.mercadolivre.com.br"),
        True,
        proxy_policy=ProxyPolicy.FALLBACK,
    ),
    "pichau": StoreConfig("pichau", "BR", "BRL", ("pichau.com.br",), True),
    "terabyteshop": StoreConfig(
        "terabyteshop", "BR", "BRL", ("terabyteshop.com.br",), True
    ),
    "shopee": StoreConfig(
        "shopee",
        "BR",
        "BRL",
        ("shopee.com.br",),
        True,
        proxy_policy=ProxyPolicy.FALLBACK,
        # Gallery URLs come from the already-fetched PDP payload (no CDN
        # download in preview). Default checkbox stays off — PDP itself is
        # browser-heavy and often proxied.
        supports_images=True,
        image_fetch_cost="high",
    ),
    "aliexpress": StoreConfig(
        "aliexpress",
        "BR",
        "BRL",
        ("aliexpress.com",),
        True,
        proxy_policy=ProxyPolicy.FALLBACK,
        image_fetch_cost="high",
    ),
    "amazon_br": StoreConfig(
        "amazon",
        "BR",
        "BRL",
        ("amazon.com.br",),
        True,
    ),
    "amazon_us": StoreConfig(
        "amazon",
        "US",
        "USD",
        ("amazon.com",),
        True,
    ),
    "bestbuy": StoreConfig("bestbuy", "US", "USD", ("bestbuy.com",), True),
    "ebay": StoreConfig("ebay", "US", "USD", ("ebay.com",)),
    "gamestop": StoreConfig("gamestop", "US", "USD", ("gamestop.com",)),
    "newegg": StoreConfig("newegg", "US", "USD", ("newegg.com",)),
    "microcenter": StoreConfig("microcenter", "US", "USD", ("microcenter.com",)),
    "nissei": StoreConfig("nissei", "PY", "PYG", ("nissei.com",), True),
    "cellshop": StoreConfig("cellshop", "PY", "PYG", ("cellshop.com",)),
    "stargames": StoreConfig("stargames", "PY", "PYG", ("stargames.com.py",)),
    "shoppingchina": StoreConfig(
        "shoppingchina",
        "PY",
        "PYG",
        ("shoppingchina.com.py", "shoppingchina.com.br"),
        True,
    ),
    "visaovip": StoreConfig(
        "visaovip",
        "PY",
        "USD",
        ("visaovip.com",),
        True,
    ),
}


def implemented_store_keys() -> tuple[str, ...]:
    """Catalog keys marked ``implemented=True`` (dynamic match / crawl targets)."""
    return tuple(key for key, config in STORE_CONFIGS.items() if config.implemented)


def resolve_store_config_by_hostname(hostname: str) -> StoreConfig | None:
    """Match a hostname to ``StoreConfig`` via registered domains (no hardcoding)."""
    host = hostname.strip().lower().removeprefix("www.")
    if not host:
        return None
    for config in STORE_CONFIGS.values():
        for domain in config.domains:
            d = domain.lower().removeprefix("www.")
            if host == d or host.endswith("." + d):
                return config
    return None
