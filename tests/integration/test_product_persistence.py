"""Optional live persistence check against DATABASE_URL (cleaned up)."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import delete, select

from scout_api.core.config import Settings, get_settings
from scout_api.core.database import create_db_engine, reset_database_cache
from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole
from scout_api.modules.matching.models import (
    CanonicalProduct,
    ProductIdentifier,
    StoreListing,
)
from scout_api.modules.matching.product_registration_service import (
    ProductRegistrationService,
)
from scout_api.modules.matching.schemas import ProductRegisterRequest

_OWNER = AuthenticatedPrincipal(
    id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.USER,
    display_name="persist-tester",
)

pytestmark = pytest.mark.integration


def _database_url() -> str | None:
    return (
        os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL") or ""
    ).strip() or None


@pytest.fixture
def pg_session():
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL / TEST_DATABASE_URL não configurada")
    # Avoid writing into production accidentally unless explicitly allowed.
    if os.environ.get("ALLOW_SUPABASE_PERSISTENCE_TEST") != "1":
        pytest.skip(
            "Defina ALLOW_SUPABASE_PERSISTENCE_TEST=1 para teste controlado "
            "de persistência (cria e apaga um registro)"
        )
    get_settings.cache_clear()
    reset_database_cache()
    settings = Settings(database_url=url)
    engine = create_db_engine(settings)
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    created_ids: list[uuid.UUID] = []
    try:
        yield session, created_ids
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        # Cleanup any products created by this test.
        for product_id in created_ids:
            session.execute(
                delete(StoreListing).where(
                    StoreListing.canonical_product_id == product_id
                )
            )
            session.execute(
                delete(ProductIdentifier).where(
                    ProductIdentifier.canonical_product_id == product_id
                )
            )
            session.execute(
                delete(CanonicalProduct).where(CanonicalProduct.id == product_id)
            )
        session.commit()
        session.close()
        engine.dispose()
        reset_database_cache()
        get_settings.cache_clear()


def test_register_product_roundtrip_on_postgres(pg_session) -> None:
    session, created_ids = pg_session
    service = ProductRegistrationService(session)
    suffix = uuid.uuid4().hex[:8]
    # Sem GTIN: dedup por store+canonical_url — evita colidir com catálogo real.
    response = service.register(
        ProductRegisterRequest(
            title=f"ScoutApiV2 persistence probe {suffix}",
            brand="ScoutTest",
            model="Probe",
            store="kabum",
            country="BR",
            product_id=f"probe-{suffix}",
            sku=f"SKU-{suffix}",
            canonical_url=f"https://www.kabum.com.br/produto/probe-{suffix}",
        ),
        owner=_OWNER,
    )
    assert response.created is True
    assert response.listing_created is True
    created_ids.append(response.product.id)

    session.flush()
    fetched = service.get_product(response.product.id)
    assert fetched is not None
    assert fetched.title == f"ScoutApiV2 persistence probe {suffix}"
    assert fetched.brand == "ScoutTest"
    assert len(fetched.listings) == 1
    assert fetched.listings[0].product_id == f"probe-{suffix}"

    again = service.register(
        ProductRegisterRequest(
            title="Nao deve sobrescrever",
            brand="Outro",
            store="kabum",
            country="BR",
            product_id=f"probe-{suffix}",
            canonical_url=f"https://www.kabum.com.br/produto/probe-{suffix}",
        ),
        owner=_OWNER,
    )
    assert again.created is False
    assert again.product.id == response.product.id
    assert again.product.title == f"ScoutApiV2 persistence probe {suffix}"

    row = session.scalars(
        select(CanonicalProduct).where(CanonicalProduct.id == response.product.id)
    ).first()
    assert row is not None
