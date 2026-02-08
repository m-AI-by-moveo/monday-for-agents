"""Unit tests for a2a_server.middleware.security and validation."""

from __future__ import annotations

import json

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from a2a_server.middleware.security import (
    RequestSizeLimitMiddleware,
    SecureHeadersMiddleware,
)
from a2a_server.middleware.validation import InputValidationMiddleware


def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


# ---------------------------------------------------------------------------
# SecureHeadersMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSecureHeadersMiddleware:
    def test_adds_security_headers(self) -> None:
        app = Starlette(routes=[Route("/", _ok)])
        app.add_middleware(SecureHeadersMiddleware)
        client = TestClient(app)

        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["cache-control"] == "no-store"
        assert "max-age=" in resp.headers["strict-transport-security"]


# ---------------------------------------------------------------------------
# RequestSizeLimitMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequestSizeLimitMiddleware:
    def test_allows_small_requests(self) -> None:
        app = Starlette(routes=[Route("/", _ok, methods=["POST"])])
        app.add_middleware(RequestSizeLimitMiddleware, max_size=1024)
        client = TestClient(app)

        resp = client.post("/", content=b"small body")
        assert resp.status_code == 200

    def test_rejects_oversized_requests(self) -> None:
        app = Starlette(routes=[Route("/", _ok, methods=["POST"])])
        app.add_middleware(RequestSizeLimitMiddleware, max_size=10)
        client = TestClient(app)

        resp = client.post("/", content=b"x" * 100, headers={"Content-Length": "100"})
        assert resp.status_code == 413
        assert "Payload Too Large" in resp.json()["error"]


# ---------------------------------------------------------------------------
# InputValidationMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInputValidationMiddleware:
    def _make_client(self) -> TestClient:
        app = Starlette(routes=[
            Route("/", _ok, methods=["POST"]),
            Route("/health", _ok),
        ])
        app.add_middleware(InputValidationMiddleware)
        return TestClient(app)

    def test_bypasses_health_paths(self) -> None:
        client = self._make_client()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_rejects_invalid_json(self) -> None:
        client = self._make_client()
        resp = client.post("/", content=b"not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == -32700

    def test_rejects_missing_jsonrpc_field(self) -> None:
        client = self._make_client()
        body = json.dumps({"method": "message/send", "id": 1})
        resp = client.post("/", content=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == -32600

    def test_rejects_unknown_method(self) -> None:
        client = self._make_client()
        body = json.dumps({"jsonrpc": "2.0", "method": "hack/system", "id": 1})
        resp = client.post("/", content=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == -32601

    def test_accepts_valid_jsonrpc(self) -> None:
        client = self._make_client()
        body = json.dumps({
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": 1,
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": "hello"}],
                }
            },
        })
        resp = client.post("/", content=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 200

    def test_rejects_oversized_message_text(self) -> None:
        client = self._make_client()
        body = json.dumps({
            "jsonrpc": "2.0",
            "method": "message/send",
            "id": 1,
            "params": {
                "message": {
                    "parts": [{"text": "x" * 60_000}],
                }
            },
        })
        resp = client.post("/", content=body, headers={"Content-Type": "application/json"})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == -32602
