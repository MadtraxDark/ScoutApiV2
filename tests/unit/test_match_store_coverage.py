"""Regression: match store resolution and scrape failures surface as ERROR."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.core.fingerprints import canonicalize_url
from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.crawler.models.search import SearchCandidate
from scout_api.modules.crawler.stores import STORE_CONFIGS
from scout_api.modules.matching.product_match_service import ProductMatchService
from scout_api.modules.matching.schemas import MatchRequest


def _item(**overrides: object) -> ProductPriceItem:
    base: dict[str, object] = {
        "store": "mercadolivre",
        "country": "BR",
        "product_id": "MLB1",
        "url": "https://www.mercadolivre.com.br/p/MLB1",
        "canonical_url": "https://www.mercadolivre.com.br/p/MLB1",
        "title": "MSI GeForce RTX 5070 Shadow 3X OC 12GB GDDR7",
        "brand": "MSI",
        "model": "RTX 5070",
        "currency": "BRL",
        "price": Decimal("5958.18"),
        "scraped_at": datetime(2026, 9, 19, tzinfo=UTC),
        "metadata": {"item_id": "MLB2", "catalog_product_id": "MLB1"},
    }
    base.update(overrides)
    return ProductPriceItem.model_validate(base)


def test_canonicalize_strips_ml_google_shopping_tracking() -> None:
    raw = (
        "https://www.mercadolivre.com.br/gpu/p/MLB47363706"
        "?pdp_filters=item_id%3AMLB6784630760"
        "&from=gshop&matt_tool=1&gclid=abc&cq_src=google_ads"
    )
    canon = canonicalize_url(raw)
    assert "pdp_filters=item_id%3AMLB6784630760" in canon
    assert "matt_tool" not in canon
    assert "gclid" not in canon
    assert "from=" not in canon
    assert "cq_src" not in canon


def test_match_includes_all_implemented_stores_dynamically() -> None:
    implemented = [k for k, cfg in STORE_CONFIGS.items() if cfg.implemented]
    assert "mercadolivre" in implemented
    assert "visaovip" in implemented

    scrape = MagicMock()
    scrape.scrape.return_value = _item()
    search = MagicMock()

    def _supported(store_key: str) -> bool:
        return store_key not in {"visaovip"}

    search.is_search_supported.side_effect = _supported
    search.search.return_value = []

    resp = ProductMatchService(scrape_service=scrape, search_service=search).match(
        MatchRequest(
            reference_url="https://www.mercadolivre.com.br/p/MLB1",
            persist=False,
        )
    )
    covered = (
        set(resp.unmatched_stores)
        | {m.store for m in resp.matches}
        | {e.store for e in resp.errors}
    )
    # Every implemented catalog key must appear as a terminal outcome.
    assert set(implemented).issubset(covered)
    assert any(
        e.code == "SEARCH_UNSUPPORTED" and e.store == "visaovip" for e in resp.errors
    )


def test_scrape_upstream_error_is_not_silent_unmatched() -> None:
    scrape = MagicMock()

    def _scrape(url: str, *, include_images: bool = False) -> ProductPriceItem:
        del include_images
        if "mercadolivre" in url:
            return _item()
        raise RequestError(
            "blocked",
            code="UPSTREAM_BLOCKED",
            url=url,
            retryable=True,
        )

    scrape.scrape.side_effect = _scrape
    search = MagicMock()
    search.is_search_supported.return_value = True
    search.search.return_value = [
        SearchCandidate(
            url="https://www.kabum.com.br/produto/1",
            title="MSI RTX 5070",
            product_id="1",
        )
    ]

    resp = ProductMatchService(scrape_service=scrape, search_service=search).match(
        MatchRequest(
            reference_url="https://www.mercadolivre.com.br/p/MLB1",
            stores=["kabum"],
            persist=False,
        )
    )
    assert "kabum" in resp.unmatched_stores
    assert any(e.store == "kabum" and e.code == "UPSTREAM_BLOCKED" for e in resp.errors)
    assert resp.matches == []
