"""Brand / model / variant identity: category-aware title parsing + search keys."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scout_api.modules.auth.schemas import AuthenticatedPrincipal, UserRole
from scout_api.modules.crawler.core.exceptions import RequestError
from scout_api.modules.crawler.models.product import ProductPriceItem
from scout_api.modules.crawler.utils.product_attributes import (
    SOURCE_SPECIFICATIONS,
    SOURCE_STRUCTURED,
    format_identity_variant,
    resolve_product_identity,
)
from scout_api.modules.crawler.utils.product_identity import (
    canonical_model_key,
    parse_title_identity,
)
from scout_api.modules.matching.db import create_all
from scout_api.modules.matching.engine import MatchingEngine
from scout_api.modules.matching.identity import identity_from_price_item
from scout_api.modules.matching.product_registration_service import (
    ProductRegistrationService,
)
from scout_api.modules.matching.schemas import ProductRegisterRequest

_OWNER = AuthenticatedPrincipal(
    id=UUID("11111111-1111-4111-8111-111111111111"),
    role=UserRole.USER,
    display_name="tester",
)


def _item(**overrides: object) -> ProductPriceItem:
    base: dict[str, object] = {
        "store": "kabum",
        "country": "BR",
        "product_id": "1",
        "url": "https://www.kabum.com.br/produto/1",
        "canonical_url": "https://www.kabum.com.br/produto/1",
        "title": "Produto",
        "currency": "BRL",
        "price": Decimal("100.00"),
        "scraped_at": datetime(2026, 9, 19, tzinfo=UTC),
    }
    base.update(overrides)
    return ProductPriceItem.model_validate(base)


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


def test_gpu_brand_after_chip_is_not_geforce() -> None:
    bundle = resolve_product_identity(
        title="Placa De Vídeo Geforce Rtx 5070 12gb Msi Shadow 3x Oc 6"
    )
    assert bundle.value("brand") == "Msi"
    assert bundle.value("model") == "GeForce RTX 5070"
    assert bundle.value("edition") == "Shadow 3X OC"


def test_asus_seo_title_fills_model_and_variant() -> None:
    bundle = resolve_product_identity(
        title="Placa De Vídeo GPU 12GB Dual Asus GeForce RTX 5070 OC Edition",
        structured={"brand": "Asus"},
    )
    assert bundle.value("brand") == "Asus"
    assert bundle.value("model") == "GeForce RTX 5070"
    assert bundle.value("edition") == "Dual OC Edition"
    assert format_identity_variant(bundle) == "Dual OC Edition"
    assert bundle.value("vram") == "12 GB"


def test_msi_and_gigabyte_gpu_identity() -> None:
    msi = resolve_product_identity(title="MSI GeForce RTX 5070 Shadow 3X OC 12GB GDDR7")
    assert msi.value("brand") in {"Msi", "MSI"}
    assert msi.value("model") == "GeForce RTX 5070"
    assert msi.value("edition") == "Shadow 3X OC"

    gigabyte = resolve_product_identity(title="Gigabyte RTX 5070 Windforce OC SFF 12GB")
    assert gigabyte.value("brand") == "Gigabyte"
    assert gigabyte.value("model") == "GeForce RTX 5070"
    assert gigabyte.value("edition") == "Windforce OC SFF"


def test_tuf_keeps_ti_in_model_not_variant() -> None:
    bundle = resolve_product_identity(
        title="ASUS TUF Gaming GeForce RTX 5070 Ti OC Edition"
    )
    assert bundle.value("brand") == "Asus"
    assert bundle.value("model") == "GeForce RTX 5070 Ti"
    assert bundle.value("edition") == "TUF Gaming OC Edition"
    assert canonical_model_key("GeForce RTX 5070") != canonical_model_key(
        "GeForce RTX 5070 Ti"
    )


def test_missing_variant_stays_null() -> None:
    bundle = resolve_product_identity(title="ASUS GeForce RTX 5070 12GB")
    assert bundle.value("brand") == "Asus"
    assert bundle.value("model") == "GeForce RTX 5070"
    assert bundle.value("edition") is None
    assert format_identity_variant(bundle) is None


def test_oc_edition_alone_is_not_a_variant() -> None:
    bundle = resolve_product_identity(title="ASUS GeForce RTX 5070 OC Edition")
    assert bundle.value("model") == "GeForce RTX 5070"
    assert bundle.value("edition") is None


def test_structured_gpu_chip_wins_over_weaker_title() -> None:
    bundle = resolve_product_identity(
        specifications={"Modelo": "GeForce RTX 5070 Ti"},
        title="Placa de vídeo RTX 5070 Dual OC",
    )
    assert bundle.value("model") == "GeForce RTX 5070 Ti"
    assert bundle.get("model").source == SOURCE_SPECIFICATIONS
    assert bundle.value("edition") == "Dual OC"


def test_structured_cooler_line_is_reclassified_to_variant() -> None:
    bundle = resolve_product_identity(
        structured={"brand": "MSI", "model": "Shadow 3X OC"},
        title="Placa de Video MSI Shadow 3X OC 12GB GeForce RTX5070 GDDR7",
    )
    assert bundle.value("model") == "GeForce RTX 5070"
    assert bundle.get("model").source != SOURCE_STRUCTURED
    assert bundle.value("edition") == "Shadow 3X OC"


def test_phone_cpu_ram_reuse_same_architecture() -> None:
    phone = resolve_product_identity(title="Apple iPhone 16 Pro 256GB Black")
    assert phone.value("brand") == "Apple"
    assert phone.value("model") == "iPhone 16 Pro"
    assert phone.value("storage") == "256 GB"
    assert phone.value("color") == "Black"
    assert phone.value("edition") is None

    cpu = resolve_product_identity(title="AMD Ryzen 7 7800X3D")
    assert cpu.value("brand") in {"AMD", "Amd"}
    assert cpu.value("model") == "Ryzen 7 7800X3D"
    assert cpu.value("edition") is None

    ram = resolve_product_identity(
        title="Kingston Fury Beast DDR5 32GB 6000MHz CL36",
        category="ram",
    )
    assert ram.value("brand") == "Kingston"
    assert ram.value("model") == "Fury Beast"
    assert ram.value("edition") is None


def test_canonical_model_aliases_collapse() -> None:
    keys = {
        canonical_model_key("Geforce RTX5070"),
        canonical_model_key("GeForce RTX 5070"),
        canonical_model_key("NVIDIA GeForce RTX5070"),
    }
    assert keys == {"rtx5070"}
    assert canonical_model_key("RTX 5070 Super") == "rtx5070super"


def test_notebook_does_not_use_laptop_gpu_as_product_model() -> None:
    bundle = resolve_product_identity(
        title="Notebook Acer Nitro V Ryzen 7 16GB RAM 512GB SSD RTX 4060 15.6 144Hz"
    )
    assert bundle.category == "notebook"
    assert bundle.value("model") != "GeForce RTX 4060"
    assert "4060" in (bundle.value("gpu_model") or "")


def test_mpn_is_not_treated_as_equivalent_variant() -> None:
    parsed_line = parse_title_identity(
        "ASUS Dual GeForce RTX 5070 OC Edition",
        category="gpu",
    )
    parsed_mpn = parse_title_identity("DUAL-RTX5070-O12G", category="gpu")
    assert parsed_line.variant_key == "dual"
    assert parsed_mpn.model is None
    assert parsed_mpn.variant_key is None


def test_gpu_edition_missing_is_not_a_match_conflict() -> None:
    engine = MatchingEngine()
    reference = identity_from_price_item(
        _item(
            brand="ASUS",
            model="GeForce RTX 5070",
            title="ASUS GeForce RTX 5070 Dual OC Edition 12GB",
        )
    )
    candidate = identity_from_price_item(
        _item(
            brand="ASUS",
            model="GeForce RTX 5070",
            title="ASUS GeForce RTX 5070 12GB GDDR7",
        )
    )
    score = engine.score(reference, candidate)
    assert not any(
        r.code in {"variant_mismatch", "critical_conflict"} for r in score.reasons
    )
    assert score.decision in {"auto_match", "review"}


def test_gpu_edition_conflict_still_rejects() -> None:
    engine = MatchingEngine()
    left = identity_from_price_item(
        _item(
            brand="MSI",
            title="MSI GeForce RTX 5070 Shadow 3X OC 12GB GDDR7",
        )
    )
    right = identity_from_price_item(
        _item(
            brand="MSI",
            title="MSI GeForce RTX 5070 Gaming Trio OC 12GB GDDR7",
        )
    )
    score = engine.score(left, right)
    assert score.decision == "reject"
    assert any("edition" in (r.detail or "") for r in score.reasons)


def test_product_search_model_without_variant_returns_all_editions(
    session: Session,
) -> None:
    service = ProductRegistrationService(session)
    samples = (
        ("ASUS Dual OC", "GeForce RTX 5070", "Dual OC Edition"),
        ("ASUS Prime OC", "GeForce RTX 5070", "Prime OC"),
        ("ASUS TUF", "GeForce RTX 5070", "TUF Gaming"),
        ("ASUS 5070 Ti", "GeForce RTX 5070 Ti", "TUF Gaming"),
    )
    for index, (title, model, variant) in enumerate(samples):
        service.register(
            ProductRegisterRequest(
                title=title,
                brand="Asus",
                model=model,
                variant=variant,
                attributes={"edition": variant},
                store="kabum",
                country="BR",
                product_id=str(index + 1),
                canonical_url=f"https://www.kabum.com.br/produto/{index + 1}",
                url=f"https://www.kabum.com.br/produto/{index + 1}",
            ),
            owner=_OWNER,
        )
    # Registration requires GTIN or store identity — product_id is set.
    session.commit()

    broad = service.search_products(
        viewer=_OWNER,
        brand="Asus",
        model="GeForce RTX 5070",
    )
    models = {item.model for item in broad.items}
    variants = {
        str((item.attributes or {}).get("edition"))
        for item in broad.items
        if item.attributes
    }
    assert "GeForce RTX 5070 Ti" not in models
    assert broad.count >= 3
    assert "Dual OC Edition" in variants
    assert "Prime OC" in variants

    narrow = service.search_products(
        viewer=_OWNER,
        brand="Asus",
        model="GeForce RTX 5070",
        variant="Dual OC Edition",
    )
    assert narrow.count == 1
    assert narrow.items[0].attributes.get("edition") == "Dual OC Edition"


def test_real_store_titles_fill_model_without_dumping_noise() -> None:
    """Titles taken from store fixtures / live-style listings across categories."""
    cases = (
        (
            "gpu",
            "Placa de Video MSI Shadow 3X OC 12GB GeForce RTX5070 GDDR7 - 912-V532-232",
            "GeForce RTX 5070",
            "Shadow 3X OC",
        ),
        (
            "gpu",
            "MSI RTX 5070 12G Shadow 3X OC NVIDIA GeForce 12GB GDDR7",
            "GeForce RTX 5070",
            "Shadow 3X OC",
        ),
        (
            "gpu",
            "Placa De Vídeo MSI RTX 5060 Ti",
            "GeForce RTX 5060 Ti",
            None,
        ),
        (
            "smartphone",
            "Celular Apple Iphone 15 128 Gb Blue Sim",
            "iPhone 15",
            None,
        ),
        (
            "smartphone",
            "Apple - iPhone 17 512GB - Lavender (Unlocked)",
            "iPhone 17",
            None,
        ),
        (
            "ram",
            "Kingston Fury Beast DDR5 32GB 6000MHz CL36",
            "Fury Beast",
            None,
        ),
        (
            "gpu",
            "Placa De Vídeo Geforce Rtx 5070 12gb Msi Shadow 3x Oc 6",
            "GeForce RTX 5070",
            "Shadow 3X OC",
        ),
        (
            "gpu",
            "Placa de Video GeForce NVIDIA PALIT RTX5070TI 16GB GAMINGPRO",
            "GeForce RTX 5070 Ti",
            "Gamingpro",
        ),
        (
            "cpu",
            "AMD Ryzen 7 7800X3D",
            "Ryzen 7 7800X3D",
            None,
        ),
    )
    filled_model = 0
    false_variant = 0
    for category, title, expected_model, expected_variant in cases:
        bundle = resolve_product_identity(title=title, category=category)
        if bundle.value("model") == expected_model:
            filled_model += 1
        else:
            raise AssertionError(
                f"{title!r}: model={bundle.value('model')!r} "
                f"expected {expected_model!r}"
            )
        got_variant = bundle.value("edition")
        if expected_variant is None and got_variant is not None:
            false_variant += 1
        assert got_variant == expected_variant
    assert filled_model == len(cases)
    assert false_variant == 0


def test_product_search_requires_a_filter(session: Session) -> None:
    service = ProductRegistrationService(session)
    with pytest.raises(RequestError) as exc:
        service.search_products(viewer=_OWNER)
    assert exc.value.code == "INVALID_REQUEST"
