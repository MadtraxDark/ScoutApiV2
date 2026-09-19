"""OpenAPI examples for Decimal monetary fields must stay short and readable."""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

_MONETARY_FIELDS = (
    "price",
    "original_price",
    "discount_percentage",
    "pix_price",
    "installment_price",
    "shipping_price",
)


def _walk(node: Any) -> list[Any]:
    if isinstance(node, dict):
        values: list[Any] = []
        for key, value in node.items():
            if key in {"example", "examples", "default"}:
                values.append(value)
            values.extend(_walk(value))
        return values
    if isinstance(node, list):
        values: list[Any] = []
        for item in node:
            values.extend(_walk(item))
        return values
    return []


def _assert_no_absurd_decimal_examples(schema: dict[str, Any]) -> None:
    for value in _walk(schema):
        candidates: list[Any]
        if isinstance(value, list):
            candidates = value
        else:
            candidates = [value]
        for item in candidates:
            if (
                isinstance(item, str)
                and len(item) > 32
                and item.replace(".", "").isdigit()
            ):
                raise AssertionError(
                    f"exemplo Decimal absurdo no OpenAPI: {item[:80]}..."
                )
            if isinstance(item, (int, float)) and abs(item) > 10**12:
                raise AssertionError(f"exemplo numérico absurdo no OpenAPI: {item}")


def test_openapi_product_schemas_have_readable_decimal_examples(
    client: TestClient,
) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi = response.json()
    schemas = openapi["components"]["schemas"]

    for name in ("ProductOffer", "ProductPriceItem"):
        schema = schemas[name]
        assert "examples" in schema
        example = schema["examples"][0]
        for field in _MONETARY_FIELDS:
            if field not in example:
                continue
            value = example[field]
            if value is None:
                continue
            assert isinstance(value, str)
            assert len(value) <= 16
            assert "0000000000" not in value

        price_prop = schema["properties"]["price"]
        assert price_prop["type"] == "string"
        assert price_prop["examples"] == ["4799.00"]

        metadata_prop = schema["properties"]["metadata"]
        assert metadata_prop["examples"][0]["source"]["price"] == "structured-data"

    confidence = schemas["MatchHit"]["properties"]["confidence"]
    assert confidence["examples"] == ["0.9700"]

    _assert_no_absurd_decimal_examples(schemas["ProductOffer"])
    _assert_no_absurd_decimal_examples(schemas["ProductPriceItem"])
    _assert_no_absurd_decimal_examples(schemas["MatchHit"])
    _assert_no_absurd_decimal_examples(schemas["OfferSnapshotView"])


def test_decimal_fields_remain_decimal_in_runtime_models() -> None:
    from decimal import Decimal

    from scout_api.modules.crawler.models.product import ProductOffer

    offer = ProductOffer(
        store="magazineluiza",
        country="BR",
        product_id="1",
        url="https://example.com/p/1",
        canonical_url="https://example.com/p/1",
        currency="BRL",
        price=Decimal("4799.00"),
        pix_price=None,
    )
    assert isinstance(offer.price, Decimal)
    payload = json.loads(offer.model_dump_json())
    assert payload["price"] == "4799.00"
    assert payload["pix_price"] is None
