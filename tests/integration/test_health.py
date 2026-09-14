import pytest
from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok_without_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "scout_api.modules.health.router.check_database",
        lambda: "not_configured",
    )

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "not_configured"
