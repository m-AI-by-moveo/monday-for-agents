"""Unit tests for a2a_server.resilience — retry and circuit breaker."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from a2a_server.resilience import CircuitBreaker, retry_with_backoff


@pytest.mark.unit
class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self) -> None:
        func = AsyncMock(return_value="ok")
        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self) -> None:
        func = AsyncMock(side_effect=[ValueError("fail"), ValueError("fail"), "ok"])
        result = await retry_with_backoff(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        func = AsyncMock(side_effect=ValueError("always fails"))
        with pytest.raises(ValueError, match="always fails"):
            await retry_with_backoff(func, max_retries=2, base_delay=0.01)
        assert func.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_forwards_args_and_kwargs(self) -> None:
        func = AsyncMock(return_value="ok")
        await retry_with_backoff(func, "a", "b", max_retries=1, base_delay=0.01, key="val")
        func.assert_awaited_once_with("a", "b", key="val")


@pytest.mark.unit
class TestCircuitBreaker:
    def test_starts_closed(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.allow_request() is False

    def test_success_resets_count(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_half_open_after_recovery_timeout(self) -> None:
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"

        # Wait for recovery timeout
        time.sleep(0.15)
        assert cb.state == "half_open"
        assert cb.allow_request() is True

    def test_half_open_to_closed_on_success(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == "half_open"

        cb.record_success()
        assert cb.state == "closed"

    def test_half_open_to_open_on_failure(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == "half_open"

        cb.record_failure()
        assert cb.state == "open"
