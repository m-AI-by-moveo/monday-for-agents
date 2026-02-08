"""Retry with exponential backoff and circuit breaker patterns."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    **kwargs: Any,
) -> Any:
    """Call an async function with exponential backoff on failure.

    Args:
        func: The async callable to retry.
        *args: Positional arguments forwarded to *func*.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds between retries.
        max_delay: Maximum delay cap in seconds.
        **kwargs: Keyword arguments forwarded to *func*.

    Returns:
        The return value of *func* on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(
                "Attempt %d/%d failed (%s), retrying in %.1fs",
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]


@dataclass
class CircuitBreaker:
    """Simple circuit breaker with failure threshold and recovery timeout.

    States:
        CLOSED  — requests pass through normally.
        OPEN    — requests are immediately rejected.
        HALF_OPEN — one probe request is allowed; success closes, failure re-opens.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0

    _failure_count: int = field(default=0, init=False, repr=False)
    _state: str = field(default="closed", init=False, repr=False)
    _opened_at: float = field(default=0.0, init=False, repr=False)

    @property
    def state(self) -> str:
        if self._state == "open":
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = "half_open"
        return self._state

    def record_success(self) -> None:
        """Record a successful call — resets the failure count and closes the circuit."""
        self._failure_count = 0
        self._state = "closed"

    def record_failure(self) -> None:
        """Record a failed call — may open the circuit."""
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker opened after %d failures", self._failure_count,
            )

    def allow_request(self) -> bool:
        """Return True if a request should be allowed through."""
        state = self.state  # triggers half_open check
        if state == "closed":
            return True
        if state == "half_open":
            return True
        return False
