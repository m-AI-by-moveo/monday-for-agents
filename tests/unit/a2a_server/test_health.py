"""Unit tests for a2a_server.health — health and readiness endpoints."""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette

from a2a_server.health import _health, _ready_check, health_routes, init_health
import a2a_server.health as health_mod


@pytest.fixture(autouse=True)
def _reset_health_state() -> None:
    """Reset health module state between tests."""
    health_mod._start_time = 0.0
    health_mod._ready = False


def _make_app() -> TestClient:
    app = Starlette(routes=health_routes)
    return TestClient(app)


@pytest.mark.unit
class TestHealthEndpoint:
    def test_health_returns_200(self) -> None:
        client = _make_app()
        init_health()
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data

    def test_health_returns_200_even_before_init(self) -> None:
        client = _make_app()
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


@pytest.mark.unit
class TestReadyEndpoint:
    def test_ready_returns_503_before_init(self) -> None:
        client = _make_app()
        resp = client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"

    def test_ready_returns_200_after_init(self) -> None:
        client = _make_app()
        init_health()
        resp = client.get("/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
