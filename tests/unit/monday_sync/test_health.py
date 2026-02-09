"""Tests for monday_sync.health."""

from __future__ import annotations

import httpx
import pytest
import respx

from a2a_server.models import A2AConfig, A2ASkill, AgentDefinition, AgentMetadata

from monday_sync.health import check_agent_health


def _make_agent(name: str = "test-agent", port: int = 19999) -> AgentDefinition:
    return AgentDefinition(
        metadata=AgentMetadata(name=name),
        a2a=A2AConfig(port=port, skills=[A2ASkill(id="s1")]),
    )


@pytest.mark.unit
class TestCheckAgentHealth:
    """Tests for check_agent_health()."""

    @respx.mock
    async def test_healthy_agent(self) -> None:
        """200 response -> healthy."""
        agent = _make_agent(port=19999)
        respx.get("http://localhost:19999/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        result = await check_agent_health(agent)
        assert result.status == "healthy"
        assert result.response_time_ms is not None
        assert result.response_time_ms >= 0

    @respx.mock
    async def test_unhealthy_agent(self) -> None:
        """Non-200 response -> unhealthy."""
        agent = _make_agent(port=19998)
        respx.get("http://localhost:19998/health").mock(
            return_value=httpx.Response(500, text="error")
        )
        result = await check_agent_health(agent)
        assert result.status == "unhealthy"
        assert "500" in result.detail

    @respx.mock
    async def test_not_running(self) -> None:
        """Connection refused -> not_running."""
        agent = _make_agent(port=19997)
        respx.get("http://localhost:19997/health").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await check_agent_health(agent)
        assert result.status == "not_running"

    @respx.mock
    async def test_timeout(self) -> None:
        """Timeout -> error with detail."""
        agent = _make_agent(port=19996)
        respx.get("http://localhost:19996/health").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )
        result = await check_agent_health(agent)
        assert result.status == "error"
        assert "Timeout" in result.detail
