"""LangChain tool that reviews a GitHub PR using gh CLI and Claude Code."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil

from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 300


def make_review_pr_tool(timeout: int = _DEFAULT_TIMEOUT) -> BaseTool:
    """Create a LangChain tool that reviews a GitHub pull request.

    The returned tool fetches the PR diff via ``gh pr diff`` and sends it
    to Claude Code CLI for a thorough code review.  The review output
    includes approval/rejection reasoning and specific file-level feedback.

    Args:
        timeout: Maximum seconds to wait for the review subprocess.

    Returns:
        A LangChain :class:`BaseTool` instance.
    """

    @tool
    async def review_pr(pr_url: str, task_requirements: str) -> str:
        """Review a GitHub pull request by analyzing its diff against task requirements.

        Args:
            pr_url: The full GitHub PR URL (e.g. https://github.com/org/repo/pull/42).
            task_requirements: The original task description and acceptance criteria
                to review the PR against.

        Returns:
            A structured review with verdict (APPROVE/REQUEST_CHANGES) and feedback.
        """
        # Verify gh CLI is available
        gh_bin = shutil.which("gh")
        if gh_bin is None:
            return (
                "Error: 'gh' CLI not found on PATH. "
                "Install GitHub CLI: https://cli.github.com/"
            )

        # Verify claude CLI is available
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            return (
                "Error: 'claude' CLI not found on PATH. "
                "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
            )

        # Fetch PR diff and metadata via gh CLI
        logger.info("Fetching PR diff for %s", pr_url)

        try:
            diff_proc = await asyncio.create_subprocess_exec(
                gh_bin, "pr", "diff", pr_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            diff_stdout, diff_stderr = await asyncio.wait_for(
                diff_proc.communicate(), timeout=30,
            )
        except asyncio.TimeoutError:
            return "Error: Timed out fetching PR diff."

        if diff_proc.returncode != 0:
            stderr_text = diff_stderr.decode(errors="replace").strip() if diff_stderr else ""
            return f"Error: Failed to fetch PR diff (exit {diff_proc.returncode}): {stderr_text}"

        diff_text = diff_stdout.decode(errors="replace").strip() if diff_stdout else ""
        if not diff_text:
            return "Error: PR diff is empty — the PR may have no changes or may not exist."

        # Fetch PR metadata (title, body, files changed)
        try:
            view_proc = await asyncio.create_subprocess_exec(
                gh_bin, "pr", "view", pr_url,
                "--json", "title,body,files,additions,deletions",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            view_stdout, _ = await asyncio.wait_for(
                view_proc.communicate(), timeout=30,
            )
        except asyncio.TimeoutError:
            view_stdout = b""

        pr_meta = ""
        if view_proc.returncode == 0 and view_stdout:
            try:
                meta = json.loads(view_stdout.decode(errors="replace"))
                pr_meta = (
                    f"PR Title: {meta.get('title', 'N/A')}\n"
                    f"PR Description: {meta.get('body', 'N/A')}\n"
                    f"Files changed: {len(meta.get('files', []))}\n"
                    f"Additions: +{meta.get('additions', '?')} "
                    f"Deletions: -{meta.get('deletions', '?')}\n"
                )
            except (json.JSONDecodeError, TypeError):
                pass

        # Truncate very large diffs to avoid overwhelming Claude Code
        max_diff_chars = 50000
        if len(diff_text) > max_diff_chars:
            diff_text = diff_text[:max_diff_chars] + "\n\n... [diff truncated, too large to review in full]"

        # Build review prompt for Claude Code
        prompt = (
            "You are a senior code reviewer. Review the following pull request.\n\n"
            f"## Task Requirements\n{task_requirements}\n\n"
        )
        if pr_meta:
            prompt += f"## PR Metadata\n{pr_meta}\n"
        prompt += (
            f"## Diff\n```diff\n{diff_text}\n```\n\n"
            "## Review Instructions\n"
            "Provide a thorough code review with:\n"
            "1. **Verdict:** APPROVE or REQUEST_CHANGES\n"
            "2. **Summary:** 2-3 sentence overview of what the PR does\n"
            "3. **Checklist:** Does it meet each acceptance criterion from the task requirements?\n"
            "4. **Issues:** List any bugs, security concerns, or logic errors (with file:line references)\n"
            "5. **Suggestions:** Optional improvements (style, performance, readability)\n"
            "6. **Missing:** Anything required by the task that is not implemented\n\n"
            "Be specific. Reference file names and line numbers from the diff.\n"
        )

        cmd = [
            claude_bin,
            "-p", prompt,
            "--output-format", "json",
            "--no-session-persistence",
        ]

        logger.info("Running Claude Code review for %s (timeout=%ds)", pr_url, timeout)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=os.environ.copy(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()  # type: ignore[union-attr]
            await proc.wait()  # type: ignore[union-attr]
            return f"Error: Code review timed out after {timeout}s."
        except FileNotFoundError:
            return "Error: 'claude' CLI not found."

        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace").strip() if stderr else ""
            return (
                f"Error: Claude Code review exited with code {proc.returncode}.\n"
                f"stderr: {stderr_text}"
            )

        # Parse JSON output; fall back to raw text
        raw = stdout.decode(errors="replace").strip() if stdout else ""
        try:
            data = json.loads(raw)
            result_text = data.get("result", raw)
            if isinstance(result_text, dict):
                result_text = result_text.get("text", str(result_text))
            return str(result_text)
        except (json.JSONDecodeError, TypeError):
            return raw if raw else "Review completed but produced no output."

    return review_pr  # type: ignore[return-value]
