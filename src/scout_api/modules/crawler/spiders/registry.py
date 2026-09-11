"""Discover store spiders from ``allowed_domains`` without hardcoding imports."""

from __future__ import annotations

import importlib
import pkgutil
from urllib.parse import urlparse

from ..core.exceptions import RequestError
from . import __name__ as spiders_package_name
from . import __path__ as spiders_package_path
from .base import BaseStoreSpider


def _spider_classes() -> tuple[type[BaseStoreSpider], ...]:
    classes: list[type[BaseStoreSpider]] = []
    seen: set[type[BaseStoreSpider]] = set()
    for module_info in pkgutil.walk_packages(
        spiders_package_path, f"{spiders_package_name}."
    ):
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseStoreSpider)
                and value is not BaseStoreSpider
                and value not in seen
                and getattr(value, "allowed_domains", None)
            ):
                seen.add(value)
                classes.append(value)
    return tuple(classes)


def _hostname_matches(hostname: str, domain: str) -> bool:
    normalized = domain.lower().removeprefix("www.")
    return hostname == normalized or hostname.endswith(f".{normalized}")


def resolve_store_spider(url: str) -> BaseStoreSpider:
    """Map a product URL hostname to the store spider adapter."""
    hostname = (urlparse(url).hostname or "").lower()
    for spider_cls in _spider_classes():
        if any(
            _hostname_matches(hostname, domain) for domain in spider_cls.allowed_domains
        ):
            return spider_cls()
    raise RequestError(
        "Nenhum spider disponível para este domínio",
        code="UNSUPPORTED_STORE",
        url=url,
    )
