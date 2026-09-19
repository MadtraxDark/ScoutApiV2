"""Unit tests for FastAPI lifespan database cleanup."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from scout_api.main import app


def test_lifespan_shutdown_disposes_database_engine() -> None:
    with patch("scout_api.main.dispose_database_engine") as dispose:
        with TestClient(app):
            dispose.assert_not_called()
        dispose.assert_called_once_with()
