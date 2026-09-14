"""Unit tests for product registration (canonical identity, no overwrite)."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.matching.db import create_all
from scout_api.modules.matching.product_registration_service import (
    ProductRegistrationService,
)
from scout_api.modules.matching.repository import MatchingRepository
from scout_api.modules.matching.schemas import ProductRegisterRequest

_OWNER = AuthenticatedPrincipal(
    id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.USER,
    display_name="tester",
)


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_repository_get_or_create_canonical_no_overwrite(session: Session) -> None:
    repo = MatchingRepository(session)
    first, created = repo.get_or_create_canonical(
        title="Produto A",
        brand="Acme",
        model="X1",
        gtin="7891991010863",
    )
    assert created is True
    second, created_again = repo.get_or_create_canonical(
        title="Titulo Diferente Que Nao Deve Sobrescrever",
        brand="Outra",
        model="Y2",
        gtin="7891991010863",
    )
    assert created_again is False
    assert second.id == first.id
    assert second.title == "Produto A"
    assert second.brand == "Acme"
    session.commit()


def test_repository_get_or_create_listing_dedup_by_url(session: Session) -> None:
    repo = MatchingRepository(session)
    product, _ = repo.get_or_create_canonical(title="P", gtin="7891991010863")
    listing, created = repo.get_or_create_listing(
        canonical=product,
        store="kabum",
        country="BR",
        product_id="123",
        url="https://www.kabum.com.br/produto/123",
        canonical_url="https://www.kabum.com.br/produto/123",
        confidence=Decimal("1.0000"),
    )
    assert created is True
    again, created_again = repo.get_or_create_listing(
        canonical=product,
        store="kabum",
        country="BR",
        product_id="999",
        url="https://www.kabum.com.br/produto/123",
        canonical_url="https://www.kabum.com.br/produto/123",
    )
    assert created_again is False
    assert again.id == listing.id
    assert again.product_id == "123"


def test_repository_dedup_by_store_country_product_id(session: Session) -> None:
    repo = MatchingRepository(session)
    product, _ = repo.get_or_create_canonical(title="P")
    first, created = repo.get_or_create_listing(
        canonical=product,
        store="amazon",
        country="BR",
        product_id="B0TESTASIN1",
        url="https://www.amazon.com.br/dp/B0TESTASIN1",
        canonical_url="https://www.amazon.com.br/dp/B0TESTASIN1",
        sku="B0TESTASIN1",
    )
    assert created is True
    # Same store identity, different URL → reuse (no duplicate).
    second, created_again = repo.get_or_create_listing(
        canonical=product,
        store="amazon",
        country="BR",
        product_id="B0TESTASIN1",
        url="https://www.amazon.com.br/gp/product/B0TESTASIN1",
        canonical_url="https://www.amazon.com.br/gp/product/B0TESTASIN1",
        sku="B0TESTASIN1",
    )
    assert created_again is False
    assert second.id == first.id


def test_repository_dedup_by_store_country_sku(session: Session) -> None:
    repo = MatchingRepository(session)
    product, _ = repo.get_or_create_canonical(title="P")
    first, created = repo.get_or_create_listing(
        canonical=product,
        store="nissei",
        country="PY",
        product_id="SKU-777",
        url="https://www.nissei.com.py/a",
        canonical_url="https://www.nissei.com.py/a",
        sku="SKU-777",
    )
    assert created is True
    second, created_again = repo.get_or_create_listing(
        canonical=product,
        store="nissei",
        country="PY",
        product_id="SKU-777-alt",
        url="https://www.nissei.com.py/b",
        canonical_url="https://www.nissei.com.py/b",
        sku="SKU-777",
    )
    assert created_again is False
    assert second.id == first.id


def test_service_register_reuses_store_product_id(session: Session) -> None:
    service = ProductRegistrationService(session)
    first = service.register(
        ProductRegisterRequest(
            title="Original",
            store="kabum",
            country="BR",
            product_id="555",
            canonical_url="https://www.kabum.com.br/produto/555",
        ),
        owner=_OWNER,
    )
    session.commit()
    second = service.register(
        ProductRegisterRequest(
            title="Outro titulo",
            store="kabum",
            country="BR",
            product_id="555",
            canonical_url="https://www.kabum.com.br/produto/555-promo",
        ),
        owner=_OWNER,
    )
    assert second.created is False
    assert second.listing_created is False
    assert second.product.id == first.product.id
    assert second.product.title == "Original"


def test_service_register_and_get(session: Session) -> None:
    service = ProductRegistrationService(session)
    response = service.register(
        ProductRegisterRequest(
            title="Notebook Teste",
            brand="Lenovo",
            model="Slim 3",
            gtin="7891991010863",
            variant="Luna Grey",
            store="kabum",
            country="BR",
            product_id="111",
            sku="SKU-111",
            canonical_url="https://www.kabum.com.br/produto/111",
        ),
        owner=_OWNER,
    )
    assert response.created is True
    assert response.listing_created is True
    assert response.product.gtins == ["7891991010863"]
    assert response.listing is not None
    session.commit()

    fetched = service.get_product(response.product.id)
    assert fetched is not None
    assert fetched.title == "Notebook Teste"
    assert len(fetched.listings) == 1


def test_service_register_existing_gtin_no_overwrite(session: Session) -> None:
    service = ProductRegistrationService(session)
    first = service.register(
        ProductRegisterRequest(title="Original", brand="Acme", gtin="7891991010863"),
        owner=_OWNER,
    )
    session.commit()
    second = service.register(
        ProductRegisterRequest(
            title="Novo Titulo",
            brand="Outra",
            gtin="7891991010863",
        ),
        owner=_OWNER,
    )
    assert second.created is False
    assert second.product.id == first.product.id
    assert second.product.title == "Original"
    assert second.product.brand == "Acme"


def test_service_requires_gtin_or_listing(session: Session) -> None:
    service = ProductRegistrationService(session)
    with pytest.raises(RequestError) as exc:
        service.register(ProductRegisterRequest(title="Sem chave"), owner=_OWNER)
    assert exc.value.code == "INVALID_REQUEST"


def test_service_rejects_invalid_gtin(session: Session) -> None:
    service = ProductRegistrationService(session)
    with pytest.raises(RequestError) as exc:
        service.register(ProductRegisterRequest(title="X", gtin="123"), owner=_OWNER)
    assert exc.value.code == "INVALID_REQUEST"


def test_service_blocks_other_owner_product(session: Session) -> None:
    service = ProductRegistrationService(session)
    first = service.register(
        ProductRegisterRequest(title="Privado", brand="Acme", gtin="7891991010863"),
        owner=_OWNER,
    )
    session.commit()
    other = AuthenticatedPrincipal(
        id=UUID("22222222-2222-4222-8222-222222222222"),
        role=UserRole.USER,
        display_name="other",
    )
    with pytest.raises(RequestError) as exc:
        service.register(
            ProductRegisterRequest(title="Hijack", gtin="7891991010863"),
            owner=other,
        )
    assert exc.value.code == "FORBIDDEN"
    assert service.get_product(first.product.id, viewer=other) is None
