"""Architecture boundary: Store Search must not import PDP spiders."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "scout_api" / "modules"


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_store_search_service_does_not_import_spiders() -> None:
    path = ROOT / "matching" / "store_search_service.py"
    imports = _imports_of(path)
    forbidden = [
        name
        for name in imports
        if "crawler.spiders" in name or name.endswith("spiders.base")
    ]
    assert not forbidden, f"StoreSearchService acoplado a spiders: {forbidden}"
    assert "scout_api.modules.crawler.spiders.base" not in imports


def test_product_spiders_do_not_import_search_adapters() -> None:
    spiders_root = ROOT / "crawler" / "spiders"
    offenders: list[str] = []
    for path in spiders_root.rglob("*.py"):
        imports = _imports_of(path)
        bad = [n for n in imports if "matching.search_adapters" in n]
        if bad:
            offenders.append(f"{path.relative_to(ROOT)}: {bad}")
    assert not offenders, "PDP spiders importaram search adapters:\n" + "\n".join(
        offenders
    )


def test_search_registry_lists_expected_stores() -> None:
    from scout_api.modules.matching.search_adapters.registry import (
        registered_search_store_keys,
        reset_search_adapter_registry,
    )

    reset_search_adapter_registry()
    keys = set(registered_search_store_keys())
    expected = {
        "aliexpress",
        "amazon_br",
        "amazon_us",
        "bestbuy",
        "kabum",
        "magazineluiza",
        "mercadolivre",
        "nissei",
        "pichau",
        "shopee",
        "shoppingchina",
        "terabyteshop",
        "visaovip",
    }
    assert keys == expected


def test_eligible_match_uses_search_registry_not_spider_flag() -> None:
    from scout_api.modules.matching.eligibility import eligible_match_store_keys

    eligible = set(eligible_match_store_keys())
    assert "visaovip" in eligible
    assert "mercadolivre" not in eligible  # match_enabled=False
    assert "shopee" not in eligible
