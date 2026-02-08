"""Health and readiness endpoints for the A2A server."""

from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

_start_time: float = 0.0
_ready: bool = False


def init_health() -> None:
    """Mark the server as ready and record the start time."""
    global _start_time, _ready
    _start_time = time.monotonic()
    _ready = True


def _health(request: Request) -> JSONResponse:
    """Liveness probe — always returns 200 if the process is running."""
    uptime = time.monotonic() - _start_time if _start_time else 0.0
    return JSONResponse(
        {"status": "healthy", "uptime_seconds": round(uptime, 2)},
        status_code=200,
    )


def _ready_check(request: Request) -> JSONResponse:
    """Readiness probe — returns 200 only after init_health() is called."""
    if _ready:
        return JSONResponse({"status": "ready"}, status_code=200)
    return JSONResponse({"status": "not_ready"}, status_code=503)


health_routes: list[Route] = [
    Route("/health", _health, methods=["GET"]),
    Route("/ready", _ready_check, methods=["GET"]),
]
