"""Unit tests for a2a_server.server — A2A Starlette app creation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from a2a_server.models import (
    A2ACapabilities,
    A2AConfig,
    A2ASkill,
    AgentDefinition,
    AgentMetadata,
    PromptConfig,
)
from a2a_server.server import _build_agent_card, create_a2a_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_def(
    *,
    name: str = "test-agent",
    display_name: str = "Test Agent",
    description: str = "A test agent",
    version: str = "1.0.0",
    port: int = 10000,
    skills: list[A2ASkill] | None = None,
    streaming: bool = False,
) -> AgentDefinition:
    """Build an AgentDefinition for server tests."""
    return AgentDefinition(
        metadata=AgentMetadata(
            name=name,
            display_name=display_name,
            description=description,
            version=version,
        ),
        a2a=A2AConfig(
            port=port,
            skills=skills or [],
            capabilities=A2ACapabilities(streaming=streaming),
        ),
    )


# ---------------------------------------------------------------------------
# _build_agent_card
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildAgentCard:
    """Tests for the _build_agent_card() helper."""

    def test_builds_card_with_correct_name(self) -> None:
        """Agent card name uses display_name when available."""
        agent_def = _make_agent_def(display_name="My Display Name")
        card = _build_agent_card(agent_def)
        assert card.name == "My Display Name"

    def test_falls_back_to_metadata_name(self) -> None:
        """When display_name is empty, the card uses metadata.name."""
        agent_def = _make_agent_def(name="fallback-name", display_name="")
        card = _build_agent_card(agent_def)
        assert card.name == "fallback-name"

    def test_builds_card_with_description(self) -> None:
        agent_def = _make_agent_def(description="Does amazing things")
        card = _build_agent_card(agent_def)
        assert card.description == "Does amazing things"

    def test_builds_card_with_correct_url(self) -> None:
        agent_def = _make_agent_def(port=12345)
        card = _build_agent_card(agent_def)
        assert card.url == "http://localhost:12345"

    def test_builds_card_with_version(self) -> None:
        agent_def = _make_agent_def(version="2.3.4")
        card = _build_agent_card(agent_def)
        assert card.version == "2.3.4"

    def test_maps_skills_correctly(self) -> None:
        """Skills from the agent definition are mapped to AgentSkill objects."""
        skills = [
            A2ASkill(id="s1", name="Skill One", description="First skill"),
            A2ASkill(id="s2", name="Skill Two", description="Second skill"),
        ]
        agent_def = _make_agent_def(skills=skills)
        card = _build_agent_card(agent_def)

        assert len(card.skills) == 2
        assert card.skills[0].id == "s1"
        assert card.skills[0].name == "Skill One"
        assert card.skills[0].description == "First skill"
        assert card.skills[1].id == "s2"
        assert card.skills[1].name == "Skill Two"

    def test_maps_empty_skills_list(self) -> None:
        agent_def = _make_agent_def(skills=[])
        card = _build_agent_card(agent_def)
        assert card.skills == []

    def test_sets_capabilities_streaming_true(self) -> None:
        agent_def = _make_agent_def(streaming=True)
        card = _build_agent_card(agent_def)
        assert card.capabilities.streaming is True

    def test_sets_capabilities_streaming_false(self) -> None:
        agent_def = _make_agent_def(streaming=False)
        card = _build_agent_card(agent_def)
        assert card.capabilities.streaming is False


# ---------------------------------------------------------------------------
# create_a2a_app
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateA2AApp:
    """Tests for create_a2a_app()."""

    @patch("a2a_server.server.A2AStarletteApplication")
    def test_returns_a2a_starlette_application(
        self, mock_app_cls: MagicMock
    ) -> None:
        """create_a2a_app() returns an A2AStarletteApplication instance."""
        mock_app_instance = MagicMock(name="FakeA2AApp")
        mock_app_cls.return_value = mock_app_instance

        agent_def = _make_agent_def()
        mock_executor = MagicMock()

        result = create_a2a_app(agent_def, mock_executor)

        assert result is mock_app_instance
        mock_app_cls.assert_called_once()

    @patch("a2a_server.server.A2AStarletteApplication")
    def test_passes_agent_card_to_application(
        self, mock_app_cls: MagicMock
    ) -> None:
        """create_a2a_app() constructs an AgentCard and passes it to the app."""
        agent_def = _make_agent_def(name="card-test", display_name="Card Test Agent")
        mock_executor = MagicMock()

        create_a2a_app(agent_def, mock_executor)

        call_kwargs = mock_app_cls.call_args[1]
        card = call_kwargs["agent_card"]
        assert card.name == "Card Test Agent"

    @patch("a2a_server.server.A2AStarletteApplication")
    def test_passes_executor_to_application(
        self, mock_app_cls: MagicMock
    ) -> None:
        """create_a2a_app() passes the executor to the app constructor."""
        agent_def = _make_agent_def()
        mock_executor = MagicMock(name="MyExecutor")

        create_a2a_app(agent_def, mock_executor)

        call_kwargs = mock_app_cls.call_args[1]
        assert call_kwargs["agent_executor"] is mock_executor

    @patch("a2a_server.server.A2AStarletteApplication")
    def test_card_has_skills_from_definition(
        self, mock_app_cls: MagicMock
    ) -> None:
        """The AgentCard passed to A2AStarletteApplication has the correct skills."""
        skills = [
            A2ASkill(id="plan", name="Plan", description="Plans tasks"),
            A2ASkill(id="execute", name="Execute", description="Executes tasks"),
        ]
        agent_def = _make_agent_def(skills=skills)
        mock_executor = MagicMock()

        create_a2a_app(agent_def, mock_executor)

        card = mock_app_cls.call_args[1]["agent_card"]
        assert len(card.skills) == 2
        assert card.skills[0].id == "plan"
        assert card.skills[1].id == "execute"

    @patch("a2a_server.server.A2AStarletteApplication")
    def test_card_capabilities_from_config(
        self, mock_app_cls: MagicMock
    ) -> None:
        """The AgentCard capabilities reflect the agent definition config."""
        agent_def = _make_agent_def(streaming=True)
        mock_executor = MagicMock()

        create_a2a_app(agent_def, mock_executor)

        card = mock_app_cls.call_args[1]["agent_card"]
        assert card.capabilities.streaming is True
