"""Central catalog: adding a store does not require changing crawler core."""

from dataclasses import dataclass

from .core.proxy_policy import ProxyPolicy


@dataclass(frozen=True)
class StoreConfig:
    key: str
    country: str
    currency: str
    domains: tuple[str, ...]
    implemented: bool = False
    proxy_policy: ProxyPolicy = ProxyPolicy.FALLBACK
    supports_images: bool = True


STORE_CONFIGS = {
    "kabum": StoreConfig("kabum", "BR", "BRL", ("kabum.com.br",), True),
    "magazineluiza": StoreConfig(
        "magazineluiza", "BR", "BRL", ("magazineluiza.com.br",), True
    ),
    "pichau": StoreConfig("pichau", "BR", "BRL", ("pichau.com.br",)),
    "terabyteshop": StoreConfig("terabyteshop", "BR", "BRL", ("terabyteshop.com.br",)),
    "shopee": StoreConfig(
        "shopee",
        "BR",
        "BRL",
        ("shopee.com.br",),
        True,
        proxy_policy=ProxyPolicy.FALLBACK,
        supports_images=False,
    ),
    "aliexpress": StoreConfig("aliexpress", "BR", "BRL", ("aliexpress.com",)),
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
}
