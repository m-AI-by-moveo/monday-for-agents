"""Per-IP token bucket rate limiting middleware."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token bucket rate limiter.

    Args:
        app: The ASGI application.
        max_tokens: Maximum burst capacity per IP.
        refill_rate: Tokens added per second.
    """

    def __init__(self, app: object, max_tokens: int = 60, refill_rate: float = 1.0) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self._buckets: dict[str, _Bucket] = {}

    def _get_bucket(self, ip: str) -> _Bucket:
        now = time.monotonic()
        bucket = self._buckets.get(ip)
        if bucket is None:
            bucket = _Bucket(tokens=float(self.max_tokens), last_refill=now)
            self._buckets[ip] = bucket
            return bucket

        # Refill tokens based on elapsed time
        elapsed = now - bucket.last_refill
        bucket.tokens = min(
            self.max_tokens,
            bucket.tokens + elapsed * self.refill_rate,
        )
        bucket.last_refill = now
        return bucket

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        ip = request.client.host if request.client else "unknown"
        bucket = self._get_bucket(ip)

        if bucket.tokens < 1.0:
            return JSONResponse(
                {"error": "Too Many Requests", "message": "Rate limit exceeded"},
                status_code=429,
            )

        bucket.tokens -= 1.0
        return await call_next(request)
