"""Integration tests for multi-agent communication.

These tests verify that the ``AgentRegistry`` and the
``send_message_to_agent`` tool work correctly when multiple agents are
registered and communicate via A2A JSON-RPC over HTTP.  External HTTP
calls are mocked with ``respx`` or ``unittest.mock``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from a2a_server.agent_loader import load_all_agents
from a2a_server.models import (
    A2AConfig,
    A2ASkill,
    AgentDefinition,
    AgentMetadata,
    LLMConfig,
    MondayConfig,
    PromptConfig,
    ToolsConfig,
)
from a2a_server.registry import AgentEntry, AgentRegistry, make_a2a_send_tool

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENTS_DIR = _PROJECT_ROOT / "agents"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_def(name: str, port: int) -> AgentDefinition:
    """Create a minimal AgentDefinition for testing."""
    return AgentDefinition(
        metadata=AgentMetadata(
            name=name,
            display_name=name.title(),
            description=f"Test agent: {name}",
        ),
        a2a=A2AConfig(
            port=port,
            skills=[A2ASkill(id="test", name="Test", description="test skill")],
        ),
        llm=LLMConfig(),
        tools=ToolsConfig(),
        monday=MondayConfig(),
        prompt=PromptConfig(system=f"You are the {name} agent."),
    )


def _build_full_registry() -> AgentRegistry:
    """Build a registry with all 4 project agents."""
    definitions = load_all_agents(_AGENTS_DIR)
    return AgentRegistry.from_definitions(definitions)


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.integration
class TestAgentRegistryFull:
    """Test AgentRegistry with all 4 agents registered."""

    def test_all_agents_registered(self) -> None:
        """Registry contains all four expected agents."""
        registry = _build_full_registry()
        entries = registry.list_agents()
        names = {e.definition.metadata.name for e in entries}
        assert names == {"product-owner", "developer", "reviewer", "scrum-master"}

    def test_each_agent_has_url(self) -> None:
        """Each agent has a resolvable URL."""
        registry = _build_full_registry()
        for entry in registry.list_agents():
            url = registry.get_agent_url(entry.definition.metadata.name)
            assert url is not None
            assert url.startswith("http://localhost:")

    def test_registry_list_agents_returns_entries(self) -> None:
        """list_agents returns AgentEntry instances with definitions and URLs."""
        registry = _build_full_registry()
        entries = registry.list_agents()
        for entry in entries:
            assert isinstance(entry, AgentEntry)
            assert isinstance(entry.definition, AgentDefinition)
            assert isinstance(entry.url, str)


@pytest.mark.integration
class TestSendMessagePayload:
    """Test send_message_to_agent tool serializes correct JSON-RPC payload."""

    async def test_correct_jsonrpc_payload(self) -> None:
        """The tool sends a well-formed JSON-RPC 2.0 message/send request."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        captured_request: httpx.Request | None = None

        async def _capture_handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_request
            captured_request = request
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "artifacts": [
                            {"parts": [{"kind": "text", "text": "Acknowledged."}]}
                        ]
                    },
                },
            )

        with respx.mock:
            respx.post("http://localhost:10002").mock(side_effect=_capture_handler)
            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Work on task #111"}
            )

        assert captured_request is not None
        payload = json.loads(captured_request.content)
        assert payload["jsonrpc"] == "2.0"
        assert payload["method"] == "message/send"
        assert payload["params"]["message"]["role"] == "user"
        parts = payload["params"]["message"]["parts"]
        assert len(parts) == 1
        assert parts[0]["kind"] == "text"
        assert parts[0]["text"] == "Work on task #111"

    async def test_agent_not_found(self) -> None:
        """Sending to an unregistered agent returns an error string."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        result = await tool.ainvoke(
            {"agent_name": "nonexistent", "message": "Hello"}
        )

        assert "not found" in result.lower()
        assert "developer" in result  # lists available agents


@pytest.mark.integration
class TestSendMessageErrorHandling:
    """Test send_message_to_agent handles network errors."""

    async def test_timeout_error(self) -> None:
        """A timeout from the target agent results in an error message."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        with respx.mock:
            respx.post("http://localhost:10002").mock(
                side_effect=httpx.ReadTimeout("Connection timed out")
            )
            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Hello"}
            )

        assert "failed" in result.lower()

    async def test_connection_refused(self) -> None:
        """A connection error results in a descriptive error message."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        with respx.mock:
            respx.post("http://localhost:10002").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Hello"}
            )

        assert "failed" in result.lower()

    async def test_http_500_error(self) -> None:
        """A 500 response from the target agent results in an error message."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        with respx.mock:
            respx.post("http://localhost:10002").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )
            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Hello"}
            )

        assert "failed" in result.lower()


@pytest.mark.integration
class TestSendMessageResponseParsing:
    """Test send_message_to_agent parses response artifacts correctly."""

    async def test_parse_artifact_text(self) -> None:
        """Text parts from response artifacts are extracted and joined."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        with respx.mock:
            respx.post("http://localhost:10002").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "artifacts": [
                                {
                                    "parts": [
                                        {"kind": "text", "text": "Part one."},
                                        {"kind": "text", "text": "Part two."},
                                    ]
                                }
                            ]
                        },
                    },
                )
            )

            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Hello"}
            )

        assert "Part one." in result
        assert "Part two." in result

    async def test_parse_multiple_artifacts(self) -> None:
        """Multiple artifacts have their text parts combined."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        with respx.mock:
            respx.post("http://localhost:10002").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "artifacts": [
                                {"parts": [{"kind": "text", "text": "First artifact."}]},
                                {"parts": [{"kind": "text", "text": "Second artifact."}]},
                            ]
                        },
                    },
                )
            )

            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Hello"}
            )

        assert "First artifact." in result
        assert "Second artifact." in result

    async def test_parse_empty_result(self) -> None:
        """A response with no artifacts falls back to string representation."""
        registry = AgentRegistry()
        registry.register(_make_agent_def("developer", 10002))
        tool = make_a2a_send_tool(registry)

        with respx.mock:
            respx.post("http://localhost:10002").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"status": "completed"},
                    },
                )
            )

            result = await tool.ainvoke(
                {"agent_name": "developer", "message": "Hello"}
            )

        # Fallback: the result dict is stringified
        assert result  # Should not be empty


@pytest.mark.integration
class TestRegistryDiscovery:
    """Test that each agent can find all other agents in the registry."""

    def test_each_agent_sees_others(self) -> None:
        """Every agent can resolve every other agent's URL."""
        registry = _build_full_registry()
        all_names = [e.definition.metadata.name for e in registry.list_agents()]

        for source_name in all_names:
            for target_name in all_names:
                url = registry.get_agent_url(target_name)
                assert url is not None, (
                    f"Agent '{source_name}' cannot discover "
                    f"agent '{target_name}'"
                )

    def test_unique_urls(self) -> None:
        """All agents have distinct URLs."""
        registry = _build_full_registry()
        urls = [e.url for e in registry.list_agents()]
        assert len(urls) == len(set(urls)), f"Duplicate URLs: {urls}"
