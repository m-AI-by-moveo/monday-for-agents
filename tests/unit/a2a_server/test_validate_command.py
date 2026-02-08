"""Unit tests for a2a_server.commands.validate — mfa validate."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from a2a_server.commands.validate import validate_command


@pytest.fixture()
def valid_yaml(tmp_path: Path) -> Path:
    content = """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: test-agent
  description: "Test agent"
a2a:
  port: 10001
prompt:
  system: "You are a test agent."
"""
    (tmp_path / "test-agent.yaml").write_text(content)
    return tmp_path


@pytest.fixture()
def invalid_yaml(tmp_path: Path) -> Path:
    (tmp_path / "bad.yaml").write_text("not: valid: yaml: [")
    return tmp_path


@pytest.fixture()
def empty_prompt_yaml(tmp_path: Path) -> Path:
    content = """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: empty-prompt
  description: "Agent with empty prompt"
a2a:
  port: 10001
prompt:
  system: ""
"""
    (tmp_path / "empty-prompt.yaml").write_text(content)
    return tmp_path


@pytest.fixture()
def collision_yaml(tmp_path: Path) -> Path:
    for name in ["agent-a", "agent-b"]:
        content = f"""\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: {name}
  description: "Collision test"
a2a:
  port: 10001
prompt:
  system: "system prompt"
"""
        (tmp_path / f"{name}.yaml").write_text(content)
    return tmp_path


@pytest.mark.unit
class TestValidateCommand:
    def test_valid_agent_passes(self, valid_yaml: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(validate_command, ["--agents-dir", str(valid_yaml)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "Valid" in result.output

    def test_invalid_yaml_fails(self, invalid_yaml: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(validate_command, ["--agents-dir", str(invalid_yaml)])
        assert result.exit_code != 0

    def test_empty_prompt_reports_issue(self, empty_prompt_yaml: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(validate_command, ["--agents-dir", str(empty_prompt_yaml)])
        assert result.exit_code != 0
        assert "prompt" in result.output.lower()

    def test_port_collision_detected(self, collision_yaml: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(validate_command, ["--agents-dir", str(collision_yaml)])
        assert result.exit_code != 0
        assert "collide" in result.output.lower() or "collision" in result.output.lower()

    def test_no_yaml_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(validate_command, ["--agents-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "No YAML" in result.output
