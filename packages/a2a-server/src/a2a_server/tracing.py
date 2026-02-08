"""Correlation ID middleware and context variable for request tracing."""

from __future__ import annotations

import contextvars
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """Return the current correlation ID, or empty string if unset."""
    return correlation_id_var.get()


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Extracts or generates an ``X-Correlation-ID`` header for every request.

    The ID is stored in a :mod:`contextvars` variable so downstream code
    can access it via :func:`get_correlation_id`.  The same header is
    echoed back in the response.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        correlation_id_var.set(cid)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
