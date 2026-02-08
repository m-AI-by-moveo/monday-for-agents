"""Unit tests for a2a_server.commands.doctor — mfa doctor."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from a2a_server.commands.doctor import doctor_command


@pytest.mark.unit
class TestDoctorCommand:
    def test_runs_without_error_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Doctor should complete without crashing."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("MONDAY_API_TOKEN", "test-token")
        monkeypatch.setenv("MONDAY_BOARD_ID", "12345")

        runner = CliRunner()
        result = runner.invoke(doctor_command, [])
        # It should produce output (checks passed or failed)
        assert "Doctor" in result.output or "Python" in result.output

    def test_reports_missing_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Doctor should report missing env vars."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("MONDAY_API_TOKEN", raising=False)
        monkeypatch.delenv("MONDAY_BOARD_ID", raising=False)

        runner = CliRunner()
        result = runner.invoke(doctor_command, [])
        assert "not set" in result.output

    def test_checks_agents_dir(self, tmp_path: Path) -> None:
        """Doctor should report when agents dir has YAML files."""
        content = """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: test
a2a:
  port: 10001
"""
        (tmp_path / "test.yaml").write_text(content)

        runner = CliRunner()
        result = runner.invoke(doctor_command, ["--agents-dir", str(tmp_path)])
        assert "test" in result.output or "agent" in result.output.lower()
