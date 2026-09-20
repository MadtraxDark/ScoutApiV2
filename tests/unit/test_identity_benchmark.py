"""Before/after style benchmark for category-aware identity (deterministic)."""

from __future__ import annotations

from scout_api.modules.crawler.utils.product_attributes import (
    format_identity_variant,
    resolve_product_identity,
)

# title, expected_category, model_contains|None, variant_ok_null|expected
_CASES: tuple[tuple[str, str, str | None, str | None], ...] = (
    (
        "Placa De Vídeo GPU 12GB Dual Asus GeForce RTX 5070 OC Edition",
        "gpu",
        "RTX 5070",
        "Dual OC Edition",
    ),
    (
        "MSI GeForce RTX 5070 Shadow 3X OC 12GB GDDR7",
        "gpu",
        "RTX 5070",
        "Shadow 3X OC",
    ),
    (
        "ASUS TUF Gaming B650M-Plus WiFi AM5 DDR5",
        "motherboard",
        "B650",
        "WiFi",
    ),
    ("AMD Ryzen 7 7800X3D", "cpu", "7800X3D", None),
    ("Apple iPhone 16 Pro 256GB Black", "smartphone", "iPhone 16 Pro", None),
    ("Samsung 990 PRO 2TB NVMe M.2 PCIe 4.0", "ssd", "990", None),
    ("PlayStation 5 Slim Digital 1TB", "console", "PlayStation 5", "Digital"),
    ("Kingston Fury Beast DDR5 32GB 6000MHz CL36", "ram", "Fury Beast", None),
    (
        "ASUS ROG Strix G16 i9-14900HX RTX 4070 16GB 1TB",
        "notebook",
        "Strix",
        None,
    ),
    ("Carregador GaN 65W USB-C", "charger", None, None),
)


def test_identity_benchmark_precision_over_null_fill() -> None:
    wrong_category = 0
    wrong_model = 0
    false_variant = 0
    ok = 0
    for title, category, model_part, variant in _CASES:
        bundle = resolve_product_identity(title=title)
        if bundle.category != category:
            wrong_category += 1
            continue
        got_model = bundle.value("model") or ""
        if model_part is not None and model_part.casefold() not in got_model.casefold():
            wrong_model += 1
            continue
        if category == "notebook" and "4070" in got_model:
            wrong_model += 1
            continue
        got_variant = format_identity_variant(bundle) or bundle.value("edition")
        if variant is None:
            # Phone/SSD may expose color/storage as public variant dimensions —
            # only fail when edition was invented for categories that should abstain.
            if category in {"gpu", "cpu", "ram", "notebook", "charger"} and got_variant:
                if category == "ram" and ":" in (got_variant or ""):
                    ok += 1
                    continue
                false_variant += 1
                continue
        elif variant.casefold() not in (got_variant or "").casefold():
            false_variant += 1
            continue
        ok += 1
    assert wrong_category == 0
    assert wrong_model == 0
    assert false_variant == 0
    assert ok >= 8
