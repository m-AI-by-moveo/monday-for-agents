"""Unit tests for a2a_server.agent_loader — YAML loading and env expansion."""

from __future__ import annotations

from pathlib import Path

import pytest

from a2a_server.agent_loader import expand_env_vars, load_agent, load_all_agents
from a2a_server.models import AgentDefinition


# ---------------------------------------------------------------------------
# expand_env_vars – string expansion
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExpandEnvVarsStrings:
    """Tests for expand_env_vars() with plain string values."""

    def test_expands_env_var_in_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """${VAR} in a string is replaced by the environment variable value."""
        monkeypatch.setenv("MY_VAR", "hello")
        result = expand_env_vars("prefix-${MY_VAR}-suffix")
        assert result == "prefix-hello-suffix"

    def test_expands_multiple_vars_in_one_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple ${VAR} placeholders in a single string are all expanded."""
        monkeypatch.setenv("A", "one")
        monkeypatch.setenv("B", "two")
        result = expand_env_vars("${A} and ${B}")
        assert result == "one and two"

    def test_leaves_string_without_pattern_unchanged(self) -> None:
        """A string that contains no ${} pattern is returned as-is."""
        result = expand_env_vars("no variables here")
        assert result == "no variables here"

    def test_replaces_missing_var_with_empty_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reference to a missing environment variable becomes ''."""
        monkeypatch.delenv("NONEXISTENT_VAR_12345", raising=False)
        result = expand_env_vars("before-${NONEXISTENT_VAR_12345}-after")
        assert result == "before--after"

    def test_returns_non_string_types_unchanged(self) -> None:
        """Non-string scalars (int, float, bool, None) pass through."""
        assert expand_env_vars(42) == 42
        assert expand_env_vars(3.14) == 3.14
        assert expand_env_vars(True) is True
        assert expand_env_vars(None) is None


# ---------------------------------------------------------------------------
# expand_env_vars – nested structures
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExpandEnvVarsNested:
    """Tests for expand_env_vars() with dicts and lists."""

    def test_handles_nested_dicts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env vars inside nested dicts are expanded recursively."""
        monkeypatch.setenv("INNER", "expanded")
        data = {"outer": {"inner": "${INNER}"}}
        result = expand_env_vars(data)
        assert result == {"outer": {"inner": "expanded"}}

    def test_handles_lists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env vars inside list elements are expanded."""
        monkeypatch.setenv("ITEM", "val")
        data = ["${ITEM}", "static", "${ITEM}"]
        result = expand_env_vars(data)
        assert result == ["val", "static", "val"]

    def test_handles_mixed_nested_structure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dicts containing lists containing dicts are expanded correctly."""
        monkeypatch.setenv("X", "xval")
        data = {"a": [{"b": "${X}"}, "literal"], "c": 123}
        result = expand_env_vars(data)
        assert result == {"a": [{"b": "xval"}, "literal"], "c": 123}

    def test_preserves_dict_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only values (not keys) of dicts are expanded."""
        monkeypatch.setenv("KEY_VAR", "ignored")
        data = {"${KEY_VAR}": "value"}
        result = expand_env_vars(data)
        # The key should remain as the literal string "${KEY_VAR}"
        assert "${KEY_VAR}" in result


# ---------------------------------------------------------------------------
# load_agent – valid files
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadAgentValid:
    """Tests for load_agent() with valid YAML inputs."""

    def test_loads_valid_yaml_file(self, sample_agent_yaml: Path) -> None:
        """load_agent() reads and validates a well-formed agent YAML."""
        agent = load_agent(sample_agent_yaml)

        assert isinstance(agent, AgentDefinition)
        assert agent.metadata.name == "test-agent"
        assert agent.metadata.display_name == "Test Agent"
        assert agent.a2a.port == 19999
        assert len(agent.a2a.skills) == 1
        assert agent.a2a.skills[0].id == "do_test"
        assert agent.llm.model == "anthropic/claude-sonnet-4-20250514"
        assert agent.llm.temperature == 0.1
        assert agent.monday.board_id == "123456789"

    def test_expands_env_vars_in_yaml(
        self,
        sample_agent_yaml_with_env: Path,
        _mock_env: None,
    ) -> None:
        """load_agent() expands ${VAR} placeholders using the environment."""
        agent = load_agent(sample_agent_yaml_with_env)

        assert agent.metadata.name == "env-agent"
        # MONDAY_BOARD_ID is set to "123456789" by the _mock_env fixture
        assert agent.monday.board_id == "123456789"
        assert "123456789" in agent.prompt.system


# ---------------------------------------------------------------------------
# load_agent – error cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadAgentErrors:
    """Tests for load_agent() with invalid inputs."""

    def test_raises_file_not_found_for_missing_file(self) -> None:
        """load_agent() raises FileNotFoundError for a non-existent path."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_agent(Path("/does/not/exist/agent.yaml"))

    def test_raises_on_invalid_yaml(self, tmp_path: Path) -> None:
        """load_agent() raises on a file with broken YAML syntax."""
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text(":\n  - :\n    invalid: [unclosed")
        with pytest.raises(Exception):
            load_agent(bad_yaml)

    def test_raises_on_empty_yaml(self, tmp_path: Path) -> None:
        """load_agent() raises ValueError for an empty YAML file."""
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")
        with pytest.raises(ValueError, match="empty"):
            load_agent(empty_yaml)

    def test_raises_on_yaml_missing_required_fields(self, tmp_path: Path) -> None:
        """load_agent() raises ValidationError when metadata.name is absent."""
        no_name = tmp_path / "no_name.yaml"
        no_name.write_text("apiVersion: mfa/v1\nkind: Agent\n")
        with pytest.raises(Exception):
            load_agent(no_name)


# ---------------------------------------------------------------------------
# load_all_agents
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadAllAgents:
    """Tests for load_all_agents()."""

    def test_loads_multiple_yaml_files(self, tmp_path: Path) -> None:
        """load_all_agents() loads every .yaml file in the directory."""
        for i in range(3):
            content = (
                f"apiVersion: mfa/v1\nkind: Agent\n"
                f"metadata:\n  name: agent-{i}\n"
            )
            (tmp_path / f"agent-{i}.yaml").write_text(content)

        agents = load_all_agents(tmp_path)
        assert len(agents) == 3
        names = {a.metadata.name for a in agents}
        assert names == {"agent-0", "agent-1", "agent-2"}

    def test_skips_invalid_files_and_continues(self, tmp_path: Path) -> None:
        """load_all_agents() skips broken files without aborting."""
        # One good file
        good = tmp_path / "good.yaml"
        good.write_text(
            "apiVersion: mfa/v1\nkind: Agent\nmetadata:\n  name: good-agent\n"
        )
        # One bad file
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: valid: yaml: {{{{")

        agents = load_all_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0].metadata.name == "good-agent"

    def test_returns_empty_list_for_empty_directory(self, tmp_path: Path) -> None:
        """load_all_agents() returns [] when no .yaml files exist."""
        agents = load_all_agents(tmp_path)
        assert agents == []

    def test_raises_for_nonexistent_directory(self) -> None:
        """load_all_agents() raises FileNotFoundError for a missing dir."""
        with pytest.raises(FileNotFoundError):
            load_all_agents(Path("/no/such/directory"))

    def test_ignores_non_yaml_files(self, tmp_path: Path) -> None:
        """load_all_agents() only picks up .yaml files, not .txt or .json."""
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.json").write_text("{}")
        (tmp_path / "agent.yaml").write_text(
            "apiVersion: mfa/v1\nkind: Agent\nmetadata:\n  name: real-agent\n"
        )

        agents = load_all_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0].metadata.name == "real-agent"
