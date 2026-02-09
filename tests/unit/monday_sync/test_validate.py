"""Tests for monday_sync.validate."""

from __future__ import annotations

from pathlib import Path

import pytest

from monday_sync.validate import Severity, ValidationReport, validate_all


@pytest.mark.unit
class TestValidateAll:
    """Tests for validate_all()."""

    def test_valid_agent_passes(self, tmp_path: Path) -> None:
        """A well-formed agent YAML produces no issues."""
        (tmp_path / "good.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: test-agent
  display_name: Test Agent
  description: A test agent
  version: "1.0.0"
  tags: [test]
a2a:
  port: 10001
  skills:
    - id: do_thing
      name: Do Thing
      description: Does the thing
tools:
  mcp_servers:
    - name: monday
      source: builtin:monday-mcp
prompt:
  system: You are a test agent.
"""
        )
        report = validate_all(tmp_path)
        assert not report.has_errors
        assert not report.has_warnings

    def test_yaml_parse_error(self, tmp_path: Path) -> None:
        """Invalid YAML produces an ERROR."""
        (tmp_path / "bad.yaml").write_text(":\n  - [invalid yaml{{{{")
        report = validate_all(tmp_path)
        assert report.has_errors
        assert report.issues[0].severity == Severity.ERROR
        assert "YAML parse error" in report.issues[0].message

    def test_schema_error(self, tmp_path: Path) -> None:
        """YAML that fails Pydantic validation produces ERROR(s)."""
        (tmp_path / "bad-schema.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
"""
        )
        report = validate_all(tmp_path)
        assert report.has_errors
        assert any("Schema error" in i.message for i in report.issues)

    def test_empty_prompt_warning(self, tmp_path: Path) -> None:
        """Agent with empty system prompt produces a WARNING."""
        (tmp_path / "no-prompt.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: no-prompt
a2a:
  port: 10005
  skills:
    - id: s1
      name: S
      description: S
prompt:
  system: ""
"""
        )
        report = validate_all(tmp_path)
        assert report.has_warnings
        assert any("Empty system prompt" in i.message for i in report.issues)

    def test_env_var_not_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reference to unset env var produces a WARNING."""
        monkeypatch.delenv("SOME_MISSING_VAR", raising=False)
        (tmp_path / "env.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: env-agent
a2a:
  port: 10006
  skills:
    - id: s1
      name: S
      description: S
monday:
  board_id: "${SOME_MISSING_VAR}"
prompt:
  system: "test"
"""
        )
        report = validate_all(tmp_path)
        assert any("SOME_MISSING_VAR" in i.message for i in report.issues)

    def test_port_out_of_range(self, tmp_path: Path) -> None:
        """Port below 1024 produces an ERROR."""
        (tmp_path / "low-port.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: low-port
a2a:
  port: 80
  skills:
    - id: s1
      name: S
      description: S
prompt:
  system: "test"
"""
        )
        report = validate_all(tmp_path)
        assert report.has_errors
        assert any("outside valid range" in i.message for i in report.issues)

    def test_unknown_mcp_source(self, tmp_path: Path) -> None:
        """Unknown builtin MCP source produces an ERROR."""
        (tmp_path / "bad-mcp.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: bad-mcp
a2a:
  port: 10007
  skills:
    - id: s1
      name: S
      description: S
tools:
  mcp_servers:
    - name: fake
      source: builtin:nonexistent-mcp
prompt:
  system: "test"
"""
        )
        report = validate_all(tmp_path)
        assert report.has_errors
        assert any("Unknown builtin MCP source" in i.message for i in report.issues)

    def test_port_conflict(self, tmp_path: Path) -> None:
        """Two agents on the same port produce an ERROR."""
        for name in ("agent-a", "agent-b"):
            (tmp_path / f"{name}.yaml").write_text(
                f"""\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: {name}
a2a:
  port: 10010
  skills:
    - id: s1
      name: S
      description: S
prompt:
  system: "test"
"""
            )
        report = validate_all(tmp_path)
        assert report.has_errors
        assert any("conflicts with" in i.message for i in report.issues)

    def test_duplicate_name(self, tmp_path: Path) -> None:
        """Two files with the same agent name produce an ERROR."""
        for fname in ("a.yaml", "b.yaml"):
            (tmp_path / fname).write_text(
                """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: same-name
a2a:
  port: 10011
  skills:
    - id: s1
      name: S
      description: S
prompt:
  system: "test"
"""
            )
        report = validate_all(tmp_path)
        assert report.has_errors
        assert any("Duplicate agent name" in i.message for i in report.issues)

    def test_no_yaml_files(self, tmp_path: Path) -> None:
        """Empty directory produces a WARNING."""
        report = validate_all(tmp_path)
        assert report.has_warnings
        assert any("No YAML files" in i.message for i in report.issues)

    def test_mixed_valid_and_invalid(self, tmp_path: Path) -> None:
        """Mix of valid and invalid files: valid ones still checked, invalid ones reported."""
        (tmp_path / "good.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: good-agent
a2a:
  port: 10020
  skills:
    - id: s1
      name: S
      description: S
prompt:
  system: "test"
"""
        )
        (tmp_path / "bad.yaml").write_text("not: valid: yaml: [[[")
        report = validate_all(tmp_path)
        assert report.has_errors
        assert report.error_count == 1  # Only the bad file

    def test_no_skills_warning(self, tmp_path: Path) -> None:
        """Agent with no skills produces a WARNING."""
        (tmp_path / "no-skills.yaml").write_text(
            """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: no-skills
a2a:
  port: 10030
prompt:
  system: "test"
"""
        )
        report = validate_all(tmp_path)
        assert report.has_warnings
        assert any("No A2A skills" in i.message for i in report.issues)

    def test_directory_does_not_exist(self, tmp_path: Path) -> None:
        """Non-existent directory produces an ERROR."""
        report = validate_all(tmp_path / "nonexistent")
        assert report.has_errors
        assert any("does not exist" in i.message for i in report.issues)


@pytest.mark.unit
class TestValidationReport:
    """Tests for ValidationReport helpers."""

    def test_empty_report(self) -> None:
        report = ValidationReport()
        assert not report.has_errors
        assert not report.has_warnings
        assert report.error_count == 0
        assert report.warning_count == 0

    def test_counts(self) -> None:
        report = ValidationReport()
        report.add("a.yaml", Severity.ERROR, "err1")
        report.add("a.yaml", Severity.ERROR, "err2")
        report.add("b.yaml", Severity.WARNING, "warn1")
        assert report.error_count == 2
        assert report.warning_count == 1
