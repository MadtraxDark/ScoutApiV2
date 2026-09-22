"""Regression: match store resolution and scrape failures surface as ERROR."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

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
    # Every implemented catalog key except the reference store must appear.
    expected = set(implemented) - {"mercadolivre"}
    assert expected.issubset(covered)
    assert "mercadolivre" not in covered
    assert any(
        e.code == "SEARCH_UNSUPPORTED" and e.store == "visaovip" for e in resp.errors
    )
    # SEARCH_UNSUPPORTED is ERROR, never silent unmatched/NO_MATCH.
    assert "visaovip" not in resp.unmatched_stores


def test_match_excludes_reference_store_even_when_requested() -> None:
    scrape = MagicMock()
    scrape.scrape.return_value = _item()
    search = MagicMock()
    search.is_search_supported.return_value = True
    search.search.return_value = []

    resp = ProductMatchService(scrape_service=scrape, search_service=search).match(
        MatchRequest(
            reference_url="https://www.mercadolivre.com.br/p/MLB1",
            stores=["mercadolivre", "kabum"],
            persist=False,
        )
    )
    searched_stores = {call.args[0] for call in search.search.call_args_list}
    assert searched_stores == {"kabum"}
    assert "mercadolivre" not in resp.unmatched_stores
    assert "kabum" in resp.unmatched_stores


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


def test_match_wave2_stores_run_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wave-2 (non-GTIN-priority) stores overlap when MATCH_STORE_CONCURRENCY > 1."""
    import threading
    import time

    from scout_api.core.config import get_settings

    monkeypatch.setenv("MATCH_STORE_CONCURRENCY", "3")
    get_settings.cache_clear()

    scrape = MagicMock()
    scrape.scrape.return_value = _item()
    search = MagicMock()
    search.is_search_supported.return_value = True

    active = 0
    peak = 0
    lock = threading.Lock()

    def _search(store_key: str, query: str, *, limit: int = 5) -> list[SearchCandidate]:
        del query, limit
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.2)
        with lock:
            active -= 1
        return []

    search.search.side_effect = _search

    t0 = time.perf_counter()
    resp = ProductMatchService(scrape_service=scrape, search_service=search).match(
        MatchRequest(
            reference_url="https://www.mercadolivre.com.br/p/MLB1",
            # kabum = wave1; remaining three = wave2 (parallel).
            stores=["kabum", "shopee", "magazineluiza", "aliexpress"],
            persist=False,
        )
    )
    elapsed = time.perf_counter() - t0

    covered = set(resp.unmatched_stores)
    assert covered == {"kabum", "shopee", "magazineluiza", "aliexpress"}
    # Three wave-2 stores overlap (each may run 2 SERP queries × sleep).
    assert peak >= 2
    # Serial wall ≈ 4 stores × 2 queries × 0.2s = 1.6s; parallel wave2 ≈ 0.8s.
    assert elapsed < 1.2

    get_settings.cache_clear()
