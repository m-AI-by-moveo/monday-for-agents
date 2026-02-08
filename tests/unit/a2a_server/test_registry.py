"""Unit tests for a2a_server.registry — agent registry and A2A send tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from a2a_server.models import A2AConfig, AgentDefinition, AgentMetadata
from a2a_server.registry import AgentEntry, AgentRegistry, make_a2a_send_tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_def(name: str = "agent-a", port: int = 10001) -> AgentDefinition:
    """Build a minimal AgentDefinition."""
    return AgentDefinition(
        metadata=AgentMetadata(name=name),
        a2a=A2AConfig(port=port),
    )


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentRegistryRegister:
    """Tests for AgentRegistry.register()."""

    def test_stores_agent_with_url(self) -> None:
        """register() saves the agent and derives the URL from the port."""
        registry = AgentRegistry()
        agent_def = _make_agent_def(name="my-agent", port=9999)
        registry.register(agent_def)

        url = registry.get_agent_url("my-agent")
        assert url == "http://localhost:9999"

    def test_overwrites_existing_agent(self) -> None:
        """Registering the same name again overwrites the previous entry."""
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="dup", port=1111))
        registry.register(_make_agent_def(name="dup", port=2222))

        assert registry.get_agent_url("dup") == "http://localhost:2222"


@pytest.mark.unit
class TestAgentRegistryGetAgentUrl:
    """Tests for AgentRegistry.get_agent_url()."""

    def test_returns_url_for_known_agent(self) -> None:
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="known", port=5000))
        assert registry.get_agent_url("known") == "http://localhost:5000"

    def test_returns_none_for_unknown_agent(self) -> None:
        registry = AgentRegistry()
        assert registry.get_agent_url("ghost") is None


@pytest.mark.unit
class TestAgentRegistryListAgents:
    """Tests for AgentRegistry.list_agents()."""

    def test_returns_all_entries(self) -> None:
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="a", port=1))
        registry.register(_make_agent_def(name="b", port=2))
        registry.register(_make_agent_def(name="c", port=3))

        entries = registry.list_agents()
        assert len(entries) == 3
        names = {e.definition.metadata.name for e in entries}
        assert names == {"a", "b", "c"}

    def test_returns_empty_list_when_no_agents(self) -> None:
        registry = AgentRegistry()
        assert registry.list_agents() == []

    def test_entries_contain_correct_url(self) -> None:
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="agent-x", port=7777))
        entries = registry.list_agents()
        assert entries[0].url == "http://localhost:7777"
        assert isinstance(entries[0], AgentEntry)


@pytest.mark.unit
class TestAgentRegistryFromDefinitions:
    """Tests for AgentRegistry.from_definitions()."""

    def test_builds_from_list(self) -> None:
        definitions = [
            _make_agent_def(name="alpha", port=100),
            _make_agent_def(name="beta", port=200),
        ]
        registry = AgentRegistry.from_definitions(definitions)

        assert registry.get_agent_url("alpha") == "http://localhost:100"
        assert registry.get_agent_url("beta") == "http://localhost:200"
        assert len(registry.list_agents()) == 2

    def test_builds_from_empty_list(self) -> None:
        registry = AgentRegistry.from_definitions([])
        assert registry.list_agents() == []


# ---------------------------------------------------------------------------
# make_a2a_send_tool
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMakeA2ASendTool:
    """Tests for make_a2a_send_tool() and the returned tool function."""

    def test_returns_a_tool(self) -> None:
        """make_a2a_send_tool() returns a LangChain BaseTool."""
        registry = AgentRegistry()
        tool = make_a2a_send_tool(registry)
        assert tool is not None
        # It should have a name (LangChain tools expose .name)
        assert hasattr(tool, "name")


@pytest.mark.unit
class TestSendMessageToAgent:
    """Tests for the send_message_to_agent tool function."""

    async def test_sends_correct_jsonrpc(self) -> None:
        """The tool posts a well-formed JSON-RPC message/send to the agent URL."""
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="target", port=5555))
        tool = make_a2a_send_tool(registry)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "artifacts": [
                    {"parts": [{"kind": "text", "text": "Agent response text"}]}
                ]
            }
        }

        with patch("a2a_server.registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await tool.ainvoke(
                {"agent_name": "target", "message": "Do this task"}
            )

        # Verify the POST was made to the correct URL
        mock_client.post.assert_awaited_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:5555"

        # Verify the JSON-RPC payload structure
        payload = call_args[1]["json"]
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "message/send"
        assert payload["params"]["message"]["parts"][0]["text"] == "Do this task"

        assert result == "Agent response text"

    async def test_returns_error_for_unknown_agent(self) -> None:
        """The tool returns a descriptive error when the agent is not registered."""
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="existing", port=1000))
        tool = make_a2a_send_tool(registry)

        result = await tool.ainvoke(
            {"agent_name": "nonexistent", "message": "Hello"}
        )

        assert "not found" in result.lower()
        assert "nonexistent" in result
        assert "existing" in result

    async def test_handles_http_errors_gracefully(self) -> None:
        """The tool returns an error message when the HTTP request fails."""
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="broken", port=6666))
        tool = make_a2a_send_tool(registry)

        with patch("a2a_server.registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPError("Connection refused")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await tool.ainvoke(
                {"agent_name": "broken", "message": "Hello"}
            )

        assert "failed" in result.lower()
        assert "broken" in result

    async def test_handles_response_with_direct_text(self) -> None:
        """The tool extracts text from result.text when no artifacts are present."""
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="simple", port=7777))
        tool = make_a2a_send_tool(registry)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "result": {"text": "Direct response"}
        }

        with patch("a2a_server.registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await tool.ainvoke(
                {"agent_name": "simple", "message": "Hello"}
            )

        assert result == "Direct response"

    async def test_handles_empty_result(self) -> None:
        """The tool returns str(result) when no text can be extracted."""
        registry = AgentRegistry()
        registry.register(_make_agent_def(name="empty", port=8888))
        tool = make_a2a_send_tool(registry)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"result": {"status": "ok"}}

        with patch("a2a_server.registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await tool.ainvoke(
                {"agent_name": "empty", "message": "Hello"}
            )

        # The fallback is str(result_dict)
        assert "status" in result
        assert "ok" in result
