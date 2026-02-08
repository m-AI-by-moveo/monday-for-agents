"""Unit tests for a2a_server.claude_code_tool — Claude Code CLI tool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from a2a_server.claude_code_tool import make_claude_code_tool


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMakeClaudeCodeTool:
    """Tests for make_claude_code_tool()."""

    def test_returns_tool_with_correct_name(self) -> None:
        """Factory returns a LangChain tool named 'run_claude_code'."""
        tool = make_claude_code_tool()
        assert tool is not None
        assert tool.name == "run_claude_code"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunClaudeCodeValidation:
    """Tests for input validation in run_claude_code."""

    async def test_error_for_nonexistent_repo_path(self, tmp_path) -> None:
        """Returns error string when repo_path does not exist."""
        tool = make_claude_code_tool()
        bad_path = str(tmp_path / "nonexistent")

        result = await tool.ainvoke(
            {"task_description": "Add a hello endpoint", "repo_path": bad_path}
        )

        assert "error" in result.lower()
        assert "nonexistent" in result

    async def test_error_for_missing_cli_binary(self, tmp_path) -> None:
        """Returns error when 'claude' binary is not on PATH."""
        tool = make_claude_code_tool()

        with patch("a2a_server.claude_code_tool.shutil.which", return_value=None):
            result = await tool.ainvoke(
                {"task_description": "Add tests", "repo_path": str(tmp_path)}
            )

        assert "error" in result.lower()
        assert "claude" in result.lower()


# ---------------------------------------------------------------------------
# Subprocess execution
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunClaudeCodeExecution:
    """Tests for subprocess execution in run_claude_code."""

    async def test_successful_execution(self, tmp_path) -> None:
        """Successful run parses JSON output and returns result text."""
        tool = make_claude_code_tool()

        json_output = '{"result": "Created PR https://github.com/org/repo/pull/42"}'

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(json_output.encode(), b"")
        )
        mock_proc.returncode = 0

        with (
            patch("a2a_server.claude_code_tool.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_tool.asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await tool.ainvoke(
                {
                    "task_description": "Add hello endpoint",
                    "repo_path": str(tmp_path),
                }
            )

        assert "https://github.com/org/repo/pull/42" in result

    async def test_nonzero_exit_code(self, tmp_path) -> None:
        """Returns error with stderr when subprocess exits non-zero."""
        tool = make_claude_code_tool()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fatal: not a git repository")
        )
        mock_proc.returncode = 1

        with (
            patch("a2a_server.claude_code_tool.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_tool.asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = await tool.ainvoke(
                {
                    "task_description": "Add feature",
                    "repo_path": str(tmp_path),
                }
            )

        assert "error" in result.lower()
        assert "exit" in result.lower() or "code 1" in result
        assert "not a git repository" in result

    async def test_timeout_handling(self, tmp_path) -> None:
        """Returns timeout error when subprocess exceeds time limit."""
        tool = make_claude_code_tool(timeout=1)

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("a2a_server.claude_code_tool.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_tool.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("a2a_server.claude_code_tool.asyncio.wait_for", side_effect=asyncio.TimeoutError()),
        ):
            result = await tool.ainvoke(
                {
                    "task_description": "Huge refactor",
                    "repo_path": str(tmp_path),
                }
            )

        assert "timed out" in result.lower()
