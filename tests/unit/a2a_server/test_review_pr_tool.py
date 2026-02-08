"""Unit tests for a2a_server.review_pr_tool — PR review tool."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_server.review_pr_tool import make_review_pr_tool


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMakeReviewPrTool:
    """Tests for make_review_pr_tool()."""

    def test_returns_tool_with_correct_name(self) -> None:
        """Factory returns a LangChain tool named 'review_pr'."""
        tool = make_review_pr_tool()
        assert tool is not None
        assert tool.name == "review_pr"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReviewPrValidation:
    """Tests for input validation in review_pr."""

    async def test_error_for_missing_gh_binary(self) -> None:
        """Returns error when 'gh' CLI is not on PATH."""
        tool = make_review_pr_tool()

        with patch("a2a_server.review_pr_tool.shutil.which", return_value=None):
            result = await tool.ainvoke(
                {
                    "pr_url": "https://github.com/org/repo/pull/1",
                    "task_requirements": "Add endpoint",
                }
            )

        assert "error" in result.lower()
        assert "gh" in result.lower()

    async def test_error_for_missing_claude_binary(self) -> None:
        """Returns error when 'claude' CLI is not on PATH."""
        tool = make_review_pr_tool()

        def selective_which(name: str) -> str | None:
            if name == "gh":
                return "/usr/bin/gh"
            return None

        with patch("a2a_server.review_pr_tool.shutil.which", side_effect=selective_which):
            result = await tool.ainvoke(
                {
                    "pr_url": "https://github.com/org/repo/pull/1",
                    "task_requirements": "Add endpoint",
                }
            )

        assert "error" in result.lower()
        assert "claude" in result.lower()


# ---------------------------------------------------------------------------
# Diff fetching
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReviewPrDiffFetch:
    """Tests for PR diff fetching."""

    async def test_error_on_diff_fetch_failure(self) -> None:
        """Returns error when gh pr diff exits non-zero."""
        tool = make_review_pr_tool()

        mock_diff_proc = AsyncMock()
        mock_diff_proc.communicate = AsyncMock(
            return_value=(b"", b"GraphQL: Could not resolve")
        )
        mock_diff_proc.returncode = 1

        with (
            patch("a2a_server.review_pr_tool.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "a2a_server.review_pr_tool.asyncio.create_subprocess_exec",
                return_value=mock_diff_proc,
            ),
        ):
            result = await tool.ainvoke(
                {
                    "pr_url": "https://github.com/org/repo/pull/999",
                    "task_requirements": "Fix bug",
                }
            )

        assert "error" in result.lower()
        assert "diff" in result.lower()

    async def test_error_on_empty_diff(self) -> None:
        """Returns error when PR diff is empty."""
        tool = make_review_pr_tool()

        mock_diff_proc = AsyncMock()
        mock_diff_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_diff_proc.returncode = 0

        with (
            patch("a2a_server.review_pr_tool.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "a2a_server.review_pr_tool.asyncio.create_subprocess_exec",
                return_value=mock_diff_proc,
            ),
        ):
            result = await tool.ainvoke(
                {
                    "pr_url": "https://github.com/org/repo/pull/1",
                    "task_requirements": "Add feature",
                }
            )

        assert "empty" in result.lower()


# ---------------------------------------------------------------------------
# Full review
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReviewPrExecution:
    """Tests for the full review subprocess execution."""

    async def test_successful_review(self) -> None:
        """Successful review returns structured verdict."""
        tool = make_review_pr_tool()

        diff_output = b"diff --git a/app.py b/app.py\n+def hello(): pass"
        view_output = json.dumps(
            {"title": "Add hello", "body": "...", "files": [{"path": "app.py"}],
             "additions": 5, "deletions": 0}
        ).encode()

        review_json = json.dumps(
            {"result": "**Verdict: APPROVE**\nCode looks good. Meets all criteria."}
        ).encode()

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            if call_count == 1:
                # gh pr diff
                proc.communicate = AsyncMock(return_value=(diff_output, b""))
                proc.returncode = 0
            elif call_count == 2:
                # gh pr view
                proc.communicate = AsyncMock(return_value=(view_output, b""))
                proc.returncode = 0
            else:
                # claude review
                proc.communicate = AsyncMock(return_value=(review_json, b""))
                proc.returncode = 0
            return proc

        with (
            patch("a2a_server.review_pr_tool.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "a2a_server.review_pr_tool.asyncio.create_subprocess_exec",
                side_effect=mock_create_subprocess,
            ),
            patch("a2a_server.review_pr_tool.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            result = await tool.ainvoke(
                {
                    "pr_url": "https://github.com/org/repo/pull/42",
                    "task_requirements": "Add hello endpoint",
                }
            )

        assert "approve" in result.lower()

    async def test_review_timeout(self) -> None:
        """Returns timeout error when Claude Code review exceeds time limit."""
        tool = make_review_pr_tool(timeout=1)

        diff_output = b"diff --git a/app.py b/app.py\n+def hello(): pass"
        view_output = b"{}"

        call_count = 0

        async def mock_create_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            proc = AsyncMock()
            if call_count <= 2:
                # gh pr diff / gh pr view
                proc.communicate = AsyncMock(
                    return_value=(diff_output if call_count == 1 else view_output, b"")
                )
                proc.returncode = 0
            else:
                # claude — will timeout
                proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
                proc.kill = MagicMock()
                proc.wait = AsyncMock()
                proc.returncode = None
            return proc

        wait_for_call_count = 0

        async def mock_wait_for(coro, timeout):
            nonlocal wait_for_call_count
            wait_for_call_count += 1
            if wait_for_call_count <= 2:
                return await coro
            raise asyncio.TimeoutError()

        with (
            patch("a2a_server.review_pr_tool.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "a2a_server.review_pr_tool.asyncio.create_subprocess_exec",
                side_effect=mock_create_subprocess,
            ),
            patch("a2a_server.review_pr_tool.asyncio.wait_for", side_effect=mock_wait_for),
        ):
            result = await tool.ainvoke(
                {
                    "pr_url": "https://github.com/org/repo/pull/42",
                    "task_requirements": "Add endpoint",
                }
            )

        assert "timed out" in result.lower()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _passthrough_wait_for(coro, timeout):
    """Pass-through wait_for that doesn't actually enforce a timeout."""
    return await coro
