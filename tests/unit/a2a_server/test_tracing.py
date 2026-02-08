"""Unit tests for a2a_server.tracing — correlation ID middleware."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from a2a_server.tracing import CorrelationMiddleware, correlation_id_var, get_correlation_id


def _echo_correlation(request: Request) -> PlainTextResponse:
    """Handler that echoes the correlation ID from the context var."""
    cid = get_correlation_id()
    return PlainTextResponse(cid)


def _make_app() -> TestClient:
    app = Starlette(routes=[Route("/echo", _echo_correlation)])
    app.add_middleware(CorrelationMiddleware)
    return TestClient(app)


@pytest.mark.unit
class TestCorrelationMiddleware:
    def test_generates_correlation_id_when_not_provided(self) -> None:
        client = _make_app()
        resp = client.get("/echo")
        assert resp.status_code == 200

        # Response should have X-Correlation-ID header
        cid = resp.headers.get("x-correlation-id")
        assert cid is not None
        assert len(cid) > 0

        # Body should echo the same ID
        assert resp.text == cid

    def test_uses_provided_correlation_id(self) -> None:
        client = _make_app()
        resp = client.get("/echo", headers={"X-Correlation-ID": "my-custom-id"})

        assert resp.status_code == 200
        assert resp.headers.get("x-correlation-id") == "my-custom-id"
        assert resp.text == "my-custom-id"

    def test_echoes_correlation_id_in_response_header(self) -> None:
        client = _make_app()
        resp = client.get("/echo", headers={"X-Correlation-ID": "req-123"})
        assert resp.headers["x-correlation-id"] == "req-123"


@pytest.mark.unit
class TestGetCorrelationId:
    def test_returns_empty_when_no_middleware(self) -> None:
        # Outside of a request, the context var should return default
        token = correlation_id_var.set("")
        try:
            assert get_correlation_id() == ""
        finally:
            correlation_id_var.reset(token)
