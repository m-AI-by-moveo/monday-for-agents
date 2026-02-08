"""Unit tests for a2a_server.middleware.auth — API key authentication."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from a2a_server.middleware.auth import APIKeyAuthMiddleware


def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _make_app() -> TestClient:
    app = Starlette(
        routes=[
            Route("/", _ok, methods=["POST"]),
            Route("/health", _ok),
            Route("/ready", _ok),
            Route("/.well-known/agent.json", _ok),
        ]
    )
    app.add_middleware(APIKeyAuthMiddleware)
    return TestClient(app)


@pytest.mark.unit
class TestAPIKeyAuthDevMode:
    """When MFA_API_KEY is not set, all requests pass through."""

    def test_allows_requests_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MFA_API_KEY", raising=False)
        client = _make_app()
        resp = client.post("/")
        assert resp.status_code == 200

    def test_allows_health_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MFA_API_KEY", raising=False)
        client = _make_app()
        resp = client.get("/health")
        assert resp.status_code == 200


@pytest.mark.unit
class TestAPIKeyAuthEnabled:
    """When MFA_API_KEY is set, auth is enforced."""

    def test_rejects_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MFA_API_KEY", "secret-key-123")
        client = _make_app()
        resp = client.post("/")
        assert resp.status_code == 401
        assert "Unauthorized" in resp.json()["error"]

    def test_rejects_wrong_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MFA_API_KEY", "secret-key-123")
        client = _make_app()
        resp = client.post("/", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_accepts_correct_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MFA_API_KEY", "secret-key-123")
        client = _make_app()
        resp = client.post("/", headers={"X-API-Key": "secret-key-123"})
        assert resp.status_code == 200
        assert resp.text == "ok"

    def test_public_paths_bypass_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MFA_API_KEY", "secret-key-123")
        client = _make_app()

        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        assert client.get("/.well-known/agent.json").status_code == 200
