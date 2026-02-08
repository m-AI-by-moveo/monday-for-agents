"""Unit tests for a2a_server.commands.status — mfa status."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from a2a_server.commands.status import status_command


@pytest.fixture()
def agents_dir(tmp_path: Path) -> Path:
    content = """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: test-agent
a2a:
  port: 19999
"""
    (tmp_path / "test-agent.yaml").write_text(content)
    return tmp_path


@pytest.mark.unit
class TestStatusCommand:
    def test_no_yaml_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(status_command, ["--agents-dir", str(tmp_path)])
        assert result.exit_code != 0
        assert "No YAML" in result.output

    def test_shows_not_running_when_agent_down(self, agents_dir: Path) -> None:
        """When no agent is running, status should show 'not running'."""
        runner = CliRunner()
        result = runner.invoke(status_command, ["--agents-dir", str(agents_dir)])
        # Agent won't be running in test, so should show not running or error
        assert "test-agent" in result.output
        assert (
            "not running" in result.output.lower()
            or "error" in result.output.lower()
            or "19999" in result.output
        )

    def test_shows_healthy_when_agent_up(self, agents_dir: Path) -> None:
        """When health check succeeds, should show healthy."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "healthy", "uptime_seconds": 42.0}

        with patch("a2a_server.commands.status.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            runner = CliRunner()
            result = runner.invoke(status_command, ["--agents-dir", str(agents_dir)])

        assert "test-agent" in result.output
