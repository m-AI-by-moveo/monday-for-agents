"""JSON-RPC input validation middleware."""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Allowed JSON-RPC methods
ALLOWED_METHODS = frozenset({
    "message/send",
    "message/stream",
    "task/get",
    "task/cancel",
})

# Maximum message text length (characters)
MAX_MESSAGE_LENGTH = 50_000

# Paths that bypass validation (non-JSON-RPC endpoints)
BYPASS_PATHS = frozenset({"/health", "/ready", "/.well-known/agent.json"})


class InputValidationMiddleware(BaseHTTPMiddleware):
    """Validates incoming JSON-RPC requests.

    Checks:
        - Valid JSON body for POST requests to JSON-RPC endpoints.
        - ``jsonrpc`` field is ``"2.0"``.
        - ``method`` is in the allowed whitelist.
        - Message text length does not exceed the maximum.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only validate POST to JSON-RPC paths
        if request.method != "POST" or request.url.path in BYPASS_PATHS:
            return await call_next(request)

        try:
            body = await request.body()
            if not body:
                return await call_next(request)

            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None},
                status_code=400,
            )

        # Validate JSON-RPC structure
        if data.get("jsonrpc") != "2.0":
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request: missing jsonrpc 2.0"}, "id": data.get("id")},
                status_code=400,
            )

        method = data.get("method", "")
        if method not in ALLOWED_METHODS:
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Method not found: {method}"}, "id": data.get("id")},
                status_code=400,
            )

        # Validate message text length
        params = data.get("params", {})
        message = params.get("message", {}) if isinstance(params, dict) else {}
        parts = message.get("parts", []) if isinstance(message, dict) else []
        for part in parts:
            if isinstance(part, dict):
                text = part.get("text", "")
                if isinstance(text, str) and len(text) > MAX_MESSAGE_LENGTH:
                    return JSONResponse(
                        {"jsonrpc": "2.0", "error": {"code": -32602, "message": f"Message text exceeds {MAX_MESSAGE_LENGTH} characters"}, "id": data.get("id")},
                        status_code=400,
                    )

        # Re-inject the body so downstream handlers can read it
        # Starlette caches the body after the first read, so this works transparently

        return await call_next(request)
