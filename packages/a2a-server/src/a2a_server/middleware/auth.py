"""API key authentication middleware."""

from __future__ import annotations

import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that bypass authentication
PUBLIC_PATHS = frozenset({"/health", "/ready", "/.well-known/agent.json"})


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates ``X-API-Key`` header against the ``MFA_API_KEY`` env var.

    If ``MFA_API_KEY`` is not set the middleware is a no-op (dev mode).
    Public paths (health, ready, agent card) always bypass auth.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        expected_key = os.environ.get("MFA_API_KEY", "")

        # No-op in dev mode (key not configured)
        if not expected_key:
            return await call_next(request)

        # Public paths bypass auth
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        provided_key = request.headers.get("x-api-key", "")
        if not provided_key or not hmac.compare_digest(provided_key, expected_key):
            return JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or missing API key"},
                status_code=401,
            )

        return await call_next(request)
