"""Unit tests for a2a_server.a2a_bridge_mcp — A2A bridge MCP server."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_server.a2a_bridge_mcp import (
    _load_registry,
    list_available_agents,
    send_message_to_agent,
)


# ---------------------------------------------------------------------------
# _load_registry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadRegistry:
    """Tests for the _load_registry() helper."""

    def test_loads_valid_json(self, monkeypatch) -> None:
        registry = {"dev": "http://localhost:10002"}
        monkeypatch.setenv("MFA_AGENT_REGISTRY", json.dumps(registry))
        result = _load_registry()
        assert result == registry

    def test_returns_empty_dict_when_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("MFA_AGENT_REGISTRY", raising=False)
        result = _load_registry()
        assert result == {}

    def test_returns_empty_dict_on_invalid_json(self, monkeypatch) -> None:
        monkeypatch.setenv("MFA_AGENT_REGISTRY", "not json")
        result = _load_registry()
        assert result == {}

    def test_returns_empty_dict_on_non_object(self, monkeypatch) -> None:
        monkeypatch.setenv("MFA_AGENT_REGISTRY", '["list", "not", "dict"]')
        result = _load_registry()
        assert result == {}


# ---------------------------------------------------------------------------
# list_available_agents
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestListAvailableAgents:
    """Tests for the list_available_agents() tool."""

    async def test_returns_registry_json(self, monkeypatch) -> None:
        registry = {
            "product-owner": "http://localhost:10001",
            "developer": "http://localhost:10002",
        }
        monkeypatch.setenv("MFA_AGENT_REGISTRY", json.dumps(registry))

        result = await list_available_agents()
        parsed = json.loads(result)
        assert parsed == registry

    async def test_returns_message_when_empty(self, monkeypatch) -> None:
        monkeypatch.delenv("MFA_AGENT_REGISTRY", raising=False)
        result = await list_available_agents()
        assert "no agents" in result.lower()


# ---------------------------------------------------------------------------
# send_message_to_agent
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSendMessageToAgent:
    """Tests for the send_message_to_agent() tool."""

    async def test_returns_error_for_unknown_agent(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "MFA_AGENT_REGISTRY",
            json.dumps({"developer": "http://localhost:10002"}),
        )
        result = await send_message_to_agent("nonexistent", "Hello")
        assert "not found" in result.lower()
        assert "developer" in result

    async def test_successful_send_returns_response(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "MFA_AGENT_REGISTRY",
            json.dumps({"target": "http://localhost:5000"}),
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "status": {
                    "state": "completed",
                    "message": {
                        "parts": [{"kind": "text", "text": "Done!"}],
                    },
                },
            },
        }

        with patch("a2a_server.a2a_bridge_mcp.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await send_message_to_agent("target", "Do task")

        assert result == "Done!"

    async def test_handles_http_error(self, monkeypatch) -> None:
        import httpx

        monkeypatch.setenv(
            "MFA_AGENT_REGISTRY",
            json.dumps({"broken": "http://localhost:6000"}),
        )

        with patch("a2a_server.a2a_bridge_mcp.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection refused"),
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await send_message_to_agent("broken", "Hello")

        assert "failed" in result.lower()
