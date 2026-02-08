"""Unit tests for a2a_server.models — Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from a2a_server.models import (
    A2ACapabilities,
    A2AConfig,
    A2ASkill,
    AgentDefinition,
    AgentMetadata,
    LLMConfig,
    MCPServerRef,
    MondayConfig,
    PromptConfig,
    ToolsConfig,
)


# ---------------------------------------------------------------------------
# AgentDefinition – valid configurations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentDefinitionValid:
    """Tests that AgentDefinition accepts well-formed data."""

    def test_complete_valid_config(self) -> None:
        """AgentDefinition validates a complete configuration with all fields."""
        agent = AgentDefinition(
            apiVersion="mfa/v1",
            kind="Agent",
            metadata=AgentMetadata(
                name="test-agent",
                display_name="Test Agent",
                description="A fully configured test agent",
                version="2.0.0",
                tags=["test", "ci"],
            ),
            a2a=A2AConfig(
                port=8080,
                skills=[
                    A2ASkill(id="skill-1", name="Skill One", description="Does one thing"),
                    A2ASkill(id="skill-2", name="Skill Two", description="Does another thing"),
                ],
                capabilities=A2ACapabilities(streaming=True),
            ),
            llm=LLMConfig(
                model="anthropic/claude-sonnet-4-20250514",
                temperature=0.5,
                max_tokens=2048,
            ),
            tools=ToolsConfig(
                mcp_servers=[
                    MCPServerRef(name="monday", source="builtin:monday-mcp"),
                ]
            ),
            monday=MondayConfig(board_id="999", default_group="In Progress"),
            prompt=PromptConfig(system="You are a helpful agent."),
        )

        assert agent.metadata.name == "test-agent"
        assert agent.metadata.display_name == "Test Agent"
        assert agent.metadata.version == "2.0.0"
        assert agent.metadata.tags == ["test", "ci"]
        assert agent.a2a.port == 8080
        assert len(agent.a2a.skills) == 2
        assert agent.a2a.capabilities.streaming is True
        assert agent.llm.temperature == 0.5
        assert agent.llm.max_tokens == 2048
        assert len(agent.tools.mcp_servers) == 1
        assert agent.monday.board_id == "999"
        assert agent.prompt.system == "You are a helpful agent."

    def test_minimal_required_fields_only_metadata_name(self) -> None:
        """AgentDefinition is valid with only the required metadata.name field."""
        agent = AgentDefinition(
            metadata=AgentMetadata(name="minimal-agent"),
        )

        assert agent.metadata.name == "minimal-agent"
        assert agent.apiVersion == "mfa/v1"
        assert agent.kind == "Agent"

    def test_agent_definition_serialisation_roundtrip(self) -> None:
        """AgentDefinition can be serialised to dict and back."""
        original = AgentDefinition(
            metadata=AgentMetadata(name="roundtrip-agent"),
            a2a=A2AConfig(port=11111),
        )
        data = original.model_dump()
        restored = AgentDefinition.model_validate(data)

        assert restored.metadata.name == original.metadata.name
        assert restored.a2a.port == original.a2a.port


# ---------------------------------------------------------------------------
# AgentMetadata defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentMetadataDefaults:
    """Tests that AgentMetadata fields have correct defaults."""

    def test_version_defaults_to_1_0_0(self) -> None:
        meta = AgentMetadata(name="agent")
        assert meta.version == "1.0.0"

    def test_tags_defaults_to_empty_list(self) -> None:
        meta = AgentMetadata(name="agent")
        assert meta.tags == []

    def test_display_name_defaults_to_empty_string(self) -> None:
        meta = AgentMetadata(name="agent")
        assert meta.display_name == ""

    def test_description_defaults_to_empty_string(self) -> None:
        meta = AgentMetadata(name="agent")
        assert meta.description == ""


# ---------------------------------------------------------------------------
# A2AConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestA2AConfigDefaults:
    """Tests that A2AConfig fields have correct defaults."""

    def test_port_defaults_to_10000(self) -> None:
        config = A2AConfig()
        assert config.port == 10000

    def test_skills_defaults_to_empty_list(self) -> None:
        config = A2AConfig()
        assert config.skills == []

    def test_capabilities_defaults_to_non_streaming(self) -> None:
        config = A2AConfig()
        assert config.capabilities.streaming is False


# ---------------------------------------------------------------------------
# LLMConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLLMConfigDefaults:
    """Tests that LLMConfig fields have correct defaults."""

    def test_model_defaults_to_anthropic_claude(self) -> None:
        config = LLMConfig()
        assert config.model == "anthropic/claude-sonnet-4-20250514"

    def test_temperature_defaults_to_0_3(self) -> None:
        config = LLMConfig()
        assert config.temperature == 0.3

    def test_max_tokens_defaults_to_4096(self) -> None:
        config = LLMConfig()
        assert config.max_tokens == 4096


# ---------------------------------------------------------------------------
# AgentDefinition – invalid configurations
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAgentDefinitionInvalid:
    """Tests that AgentDefinition rejects malformed data."""

    def test_rejects_missing_metadata(self) -> None:
        """AgentDefinition requires a metadata block."""
        with pytest.raises(ValidationError):
            AgentDefinition()  # type: ignore[call-arg]

    def test_rejects_missing_metadata_name(self) -> None:
        """AgentDefinition requires metadata.name."""
        with pytest.raises(ValidationError):
            AgentDefinition(metadata=AgentMetadata())  # type: ignore[call-arg]

    def test_rejects_invalid_apiversion_type(self) -> None:
        """apiVersion must be a string."""
        with pytest.raises(ValidationError):
            AgentDefinition(
                apiVersion=123,  # type: ignore[arg-type]
                metadata=AgentMetadata(name="agent"),
            )

    def test_rejects_invalid_kind_type(self) -> None:
        """kind must be a string."""
        with pytest.raises(ValidationError):
            AgentDefinition(
                kind=456,  # type: ignore[arg-type]
                metadata=AgentMetadata(name="agent"),
            )


# ---------------------------------------------------------------------------
# A2ASkill validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestA2ASkillValidation:
    """Tests for A2ASkill model."""

    def test_requires_id_field(self) -> None:
        """A2ASkill must have an id."""
        with pytest.raises(ValidationError):
            A2ASkill()  # type: ignore[call-arg]

    def test_accepts_id_only(self) -> None:
        """A2ASkill is valid with only an id."""
        skill = A2ASkill(id="my-skill")
        assert skill.id == "my-skill"
        assert skill.name == ""
        assert skill.description == ""

    def test_accepts_all_fields(self) -> None:
        skill = A2ASkill(id="s1", name="Skill One", description="Does stuff")
        assert skill.id == "s1"
        assert skill.name == "Skill One"
        assert skill.description == "Does stuff"


# ---------------------------------------------------------------------------
# MCPServerRef validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMCPServerRefValidation:
    """Tests for MCPServerRef model."""

    def test_requires_both_name_and_source(self) -> None:
        """MCPServerRef requires both name and source fields."""
        with pytest.raises(ValidationError):
            MCPServerRef()  # type: ignore[call-arg]

    def test_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            MCPServerRef(source="builtin:monday-mcp")  # type: ignore[call-arg]

    def test_requires_source(self) -> None:
        with pytest.raises(ValidationError):
            MCPServerRef(name="monday")  # type: ignore[call-arg]

    def test_accepts_valid_name_and_source(self) -> None:
        ref = MCPServerRef(name="monday", source="builtin:monday-mcp")
        assert ref.name == "monday"
        assert ref.source == "builtin:monday-mcp"


# ---------------------------------------------------------------------------
# MondayConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMondayConfigDefaults:
    """Tests for MondayConfig default values."""

    def test_board_id_defaults_to_empty_string(self) -> None:
        config = MondayConfig()
        assert config.board_id == ""

    def test_default_group_defaults_to_todo(self) -> None:
        config = MondayConfig()
        assert config.default_group == "To Do"


# ---------------------------------------------------------------------------
# PromptConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPromptConfigDefaults:
    """Tests for PromptConfig default values."""

    def test_system_defaults_to_empty_string(self) -> None:
        config = PromptConfig()
        assert config.system == ""

    def test_accepts_system_prompt(self) -> None:
        config = PromptConfig(system="You are helpful.")
        assert config.system == "You are helpful."
