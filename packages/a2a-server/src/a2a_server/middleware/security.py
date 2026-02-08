"""Request size limiting and secure HTTP headers middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# 1 MB default limit
DEFAULT_MAX_SIZE = 1_048_576


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects requests whose ``Content-Length`` exceeds a configurable limit.

    Args:
        app: The ASGI application.
        max_size: Maximum allowed body size in bytes.
    """

    def __init__(self, app: object, max_size: int = DEFAULT_MAX_SIZE) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.max_size = max_size

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return JSONResponse(
                {
                    "error": "Payload Too Large",
                    "message": f"Request body exceeds {self.max_size} bytes",
                },
                status_code=413,
            )
        return await call_next(request)


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response.

    Headers added:
        X-Content-Type-Options: nosniff
        X-Frame-Options: DENY
        Cache-Control: no-store
        Strict-Transport-Security: max-age=63072000; includeSubDomains
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains"
        )
        return response
