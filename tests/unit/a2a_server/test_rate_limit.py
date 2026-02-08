"""Unit tests for a2a_server.middleware.rate_limit — rate limiting."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from a2a_server.middleware.rate_limit import RateLimitMiddleware


def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _make_app(max_tokens: int = 5, refill_rate: float = 0.0) -> TestClient:
    """Create test app with rate limiter.

    Args:
        max_tokens: Burst capacity.
        refill_rate: Set to 0 so tokens don't refill during tests.
    """
    app = Starlette(routes=[Route("/", _ok)])
    app.add_middleware(RateLimitMiddleware, max_tokens=max_tokens, refill_rate=refill_rate)
    return TestClient(app)


@pytest.mark.unit
class TestRateLimitMiddleware:
    def test_allows_requests_within_limit(self) -> None:
        client = _make_app(max_tokens=3)
        for _ in range(3):
            resp = client.get("/")
            assert resp.status_code == 200

    def test_returns_429_when_limit_exceeded(self) -> None:
        client = _make_app(max_tokens=2)
        client.get("/")
        client.get("/")
        resp = client.get("/")
        assert resp.status_code == 429
        data = resp.json()
        assert "Rate limit" in data["message"]

    def test_refills_tokens_over_time(self) -> None:
        # With a high refill rate, tokens replenish quickly
        client = _make_app(max_tokens=1, refill_rate=10000.0)
        resp1 = client.get("/")
        assert resp1.status_code == 200
        # Even after consuming the token, refill rate is so high it should work
        resp2 = client.get("/")
        assert resp2.status_code == 200
