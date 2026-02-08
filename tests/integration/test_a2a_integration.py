"""Integration tests for A2A server components.

These tests verify that agent YAML files in the ``agents/`` directory
can be loaded, validated, and converted into working ``AgentDefinition``
instances.  They exercise the real ``agent_loader`` and ``models``
modules against the actual YAML files shipped with the project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from a2a_server.agent_loader import expand_env_vars, load_agent, load_all_agents
from a2a_server.models import AgentDefinition
from a2a_server.registry import AgentRegistry

# The canonical agents directory at the repo root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENTS_DIR = _PROJECT_ROOT / "agents"

# All four agent YAML files expected in the project.
_EXPECTED_AGENTS = ["product-owner", "developer", "reviewer", "scrum-master"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_all() -> list[AgentDefinition]:
    """Load all agent definitions from the canonical agents directory."""
    return load_all_agents(_AGENTS_DIR)


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.integration
class TestLoadSingleAgent:
    """Test loading a real agent YAML produces a valid AgentDefinition."""

    @pytest.mark.parametrize("agent_name", _EXPECTED_AGENTS)
    def test_load_real_agent(self, agent_name: str) -> None:
        """Each agent YAML loads into a valid AgentDefinition."""
        yaml_path = _AGENTS_DIR / f"{agent_name}.yaml"
        assert yaml_path.exists(), f"Agent file missing: {yaml_path}"

        agent_def = load_agent(yaml_path)

        assert isinstance(agent_def, AgentDefinition)
        assert agent_def.metadata.name == agent_name
        assert agent_def.apiVersion == "mfa/v1"
        assert agent_def.kind == "Agent"


@pytest.mark.integration
class TestAgentRegistryFromYAML:
    """Test AgentRegistry built from real YAML files."""

    def test_registry_has_correct_urls(self) -> None:
        """Registry derived from real YAMLs maps names to localhost URLs."""
        definitions = _load_all()
        registry = AgentRegistry.from_definitions(definitions)

        for agent_def in definitions:
            name = agent_def.metadata.name
            url = registry.get_agent_url(name)
            assert url is not None, f"Agent '{name}' not found in registry"
            assert url == f"http://localhost:{agent_def.a2a.port}"

    def test_registry_agent_count(self) -> None:
        """All four agents are registered."""
        definitions = _load_all()
        registry = AgentRegistry.from_definitions(definitions)
        assert len(registry.list_agents()) == 4

    def test_unknown_agent_returns_none(self) -> None:
        """Looking up an unregistered agent returns None."""
        definitions = _load_all()
        registry = AgentRegistry.from_definitions(definitions)
        assert registry.get_agent_url("nonexistent-agent") is None


@pytest.mark.integration
class TestEnvVarExpansion:
    """Test agent YAML env var expansion works with real env vars."""

    def test_board_id_expanded(self) -> None:
        """The ${MONDAY_BOARD_ID} placeholder is expanded from the environment.

        The shared conftest sets MONDAY_BOARD_ID=123456789 for all tests.
        """
        yaml_path = _AGENTS_DIR / "product-owner.yaml"
        agent_def = load_agent(yaml_path)

        # The conftest sets MONDAY_BOARD_ID to "123456789"
        assert agent_def.monday.board_id == "123456789"

    def test_expand_env_vars_in_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """expand_env_vars replaces ${VAR} with the env var value."""
        monkeypatch.setenv("TEST_VAR_XYZ", "hello-world")
        result = expand_env_vars("prefix-${TEST_VAR_XYZ}-suffix")
        assert result == "prefix-hello-world-suffix"

    def test_expand_env_vars_missing(self) -> None:
        """Missing env vars are replaced with empty string."""
        result = expand_env_vars("${DEFINITELY_NOT_SET_12345}")
        assert result == ""

    def test_expand_env_vars_nested_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Expansion works recursively through dicts and lists."""
        monkeypatch.setenv("NESTED_VAL", "42")
        data: dict[str, Any] = {
            "outer": {
                "inner": "${NESTED_VAL}",
                "list": ["${NESTED_VAL}", "literal"],
            }
        }
        result = expand_env_vars(data)
        assert result["outer"]["inner"] == "42"
        assert result["outer"]["list"] == ["42", "literal"]

    def test_sample_yaml_with_env_fixture(
        self,
        sample_agent_yaml_with_env: Path,
    ) -> None:
        """The sample_agent_yaml_with_env fixture loads with env expansion."""
        agent_def = load_agent(sample_agent_yaml_with_env)
        assert agent_def.monday.board_id == "123456789"
        assert "123456789" in agent_def.prompt.system


@pytest.mark.integration
class TestAllAgentYAMLs:
    """Test all 4 agent YAML files load without errors."""

    def test_all_agents_load(self) -> None:
        """load_all_agents returns exactly 4 definitions from the agents dir."""
        definitions = _load_all()
        assert len(definitions) == 4

    def test_all_agent_names_present(self) -> None:
        """Every expected agent name is present."""
        definitions = _load_all()
        loaded_names = {d.metadata.name for d in definitions}
        for expected in _EXPECTED_AGENTS:
            assert expected in loaded_names, f"Agent '{expected}' not loaded"


@pytest.mark.integration
class TestAgentYAMLRequiredFields:
    """Test all agent YAMLs have required fields."""

    @pytest.mark.parametrize("agent_name", _EXPECTED_AGENTS)
    def test_has_a2a_port(self, agent_name: str) -> None:
        """Every agent YAML has an a2a.port set."""
        agent_def = load_agent(_AGENTS_DIR / f"{agent_name}.yaml")
        assert agent_def.a2a.port > 0

    @pytest.mark.parametrize("agent_name", _EXPECTED_AGENTS)
    def test_has_llm_model(self, agent_name: str) -> None:
        """Every agent YAML has an llm.model set."""
        agent_def = load_agent(_AGENTS_DIR / f"{agent_name}.yaml")
        assert agent_def.llm.model
        assert "/" in agent_def.llm.model  # provider/model format

    @pytest.mark.parametrize("agent_name", _EXPECTED_AGENTS)
    def test_has_system_prompt(self, agent_name: str) -> None:
        """Every agent YAML has a non-empty system prompt."""
        agent_def = load_agent(_AGENTS_DIR / f"{agent_name}.yaml")
        assert agent_def.prompt.system.strip()

    @pytest.mark.parametrize("agent_name", _EXPECTED_AGENTS)
    def test_has_metadata(self, agent_name: str) -> None:
        """Every agent has display_name, description, and version."""
        agent_def = load_agent(_AGENTS_DIR / f"{agent_name}.yaml")
        assert agent_def.metadata.display_name
        assert agent_def.metadata.description
        assert agent_def.metadata.version

    @pytest.mark.parametrize("agent_name", _EXPECTED_AGENTS)
    def test_has_skills(self, agent_name: str) -> None:
        """Every agent defines at least one A2A skill."""
        agent_def = load_agent(_AGENTS_DIR / f"{agent_name}.yaml")
        assert len(agent_def.a2a.skills) >= 1


@pytest.mark.integration
class TestNoPortConflicts:
    """Test no port conflicts between agents."""

    def test_unique_ports(self) -> None:
        """All agents listen on distinct ports."""
        definitions = _load_all()
        ports = [d.a2a.port for d in definitions]
        assert len(ports) == len(set(ports)), f"Port conflict detected: {ports}"

    def test_ports_in_expected_range(self) -> None:
        """All agent ports are in the 10000-10099 range."""
        definitions = _load_all()
        for d in definitions:
            assert 10000 <= d.a2a.port < 10100, (
                f"Agent '{d.metadata.name}' port {d.a2a.port} "
                f"is outside the expected range [10000, 10100)"
            )
