import os

import pytest
from fastapi.testclient import TestClient

from scout_api.core.config import get_settings
from scout_api.core.rate_limit import reset_rate_limiter
from scout_api.main import app


@pytest.fixture(autouse=True)
def _default_test_security_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing integration/unit HTTP tests run with auth optional (non-production).

    Security suite re-enables AUTH_REQUIRED=true explicitly.
    """
    if os.environ.get("SCOUT_SECURITY_TESTS") == "1":
        yield
        return
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    get_settings.cache_clear()
    reset_rate_limiter()
    yield
    get_settings.cache_clear()
    reset_rate_limiter()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
