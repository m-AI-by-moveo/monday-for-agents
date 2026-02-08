"""Unit tests for a2a_server.registry — agent registry."""

from __future__ import annotations

import pytest

from a2a_server.models import A2AConfig, AgentDefinition, AgentMetadata
from a2a_server.registry import AgentEntry, AgentRegistry


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
