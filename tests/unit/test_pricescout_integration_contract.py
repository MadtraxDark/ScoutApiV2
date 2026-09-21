"""Contract tests for PriceScout integration endpoints and CORS."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from scout_api.core.config import get_settings
from scout_api.core.rate_limit import reset_rate_limiter
from scout_api.main import app


@pytest.fixture
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    secret = "test-hs256-secret-for-pricescout-contract"
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", secret)
    monkeypatch.setenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()
    reset_rate_limiter()
    yield secret
    get_settings.cache_clear()
    reset_rate_limiter()


def _mint(secret: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(uuid4()),
            "aud": "authenticated",
            "exp": now + timedelta(minutes=15),
            "iat": now,
            "app_metadata": {"provider": "google"},
            "user_metadata": {"full_name": "Contract User"},
        },
        secret,
        algorithm="HS256",
    )


def test_cors_preflight_allows_patch_delete_and_authorization(
    auth_settings: str,
) -> None:
    client = TestClient(app)
    for method in ("PATCH", "DELETE"):
        response = client.options(
            "/products/00000000-0000-0000-0000-000000000001",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code in {200, 204}
        assert (
            response.headers.get("access-control-allow-origin")
            == "http://localhost:3000"
        )
        allow_methods = response.headers.get("access-control-allow-methods", "")
        assert method in allow_methods
        allow_headers = response.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allow_headers


def test_stores_requires_auth(auth_settings: str) -> None:
    client = TestClient(app)
    assert client.get("/stores").status_code == 401


def test_stores_lists_registry(auth_settings: str) -> None:
    client = TestClient(app)
    token = _mint(auth_settings)
    response = client.get(
        "/stores", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "stores" in body
    assert any(item["key"] == "kabum" for item in body["stores"])
    kabum = next(item for item in body["stores"] if item["key"] == "kabum")
    assert kabum["implemented"] is True
    assert kabum["country"] == "BR"
    assert "kabum.com.br" in kabum["domains"]


def test_products_list_requires_auth(auth_settings: str) -> None:
    client = TestClient(app)
    assert client.get("/products").status_code == 401


def test_openapi_includes_pricescout_routes(auth_settings: str) -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/products" in paths
    assert "get" in paths["/products"]
    assert "patch" in paths["/products/{product_id}"]
    assert "delete" in paths["/products/{product_id}"]
    assert "/stores" in paths
    assert "/match/stream" in paths
