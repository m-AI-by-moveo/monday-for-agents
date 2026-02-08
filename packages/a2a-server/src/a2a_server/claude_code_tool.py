"""LangChain tool that invokes Claude Code CLI to implement tasks."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

# Default timeout for Claude Code subprocess (5 minutes)
_DEFAULT_TIMEOUT = 300


def make_claude_code_tool(timeout: int = _DEFAULT_TIMEOUT) -> BaseTool:
    """Create a LangChain tool that runs Claude Code CLI to implement code.

    The returned tool invokes ``claude -p`` as a subprocess, passing a
    task description as a prompt.  Claude Code handles the implementation,
    git commit, and PR creation autonomously.

    Args:
        timeout: Maximum seconds to wait for the subprocess.

    Returns:
        A LangChain :class:`BaseTool` instance.
    """

    @tool
    async def run_claude_code(task_description: str, repo_path: str) -> str:
        """Run Claude Code CLI to implement a coding task, commit changes, and create a PR.

        Args:
            task_description: Detailed description of the task to implement.
                Include requirements, acceptance criteria, and any relevant context.
            repo_path: Absolute path to the git repository where code should be written.

        Returns:
            The Claude Code output (including PR URL on success) or an error description.
        """
        # Validate repo path
        repo = Path(repo_path)
        if not repo.is_dir():
            return f"Error: repo_path '{repo_path}' does not exist or is not a directory."

        # Verify claude CLI is available
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            return (
                "Error: 'claude' CLI not found on PATH. "
                "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
            )

        # Build the prompt for Claude Code
        prompt = (
            f"You are working in the repository at {repo_path}.\n\n"
            f"## Task\n{task_description}\n\n"
            "## Instructions\n"
            "1. Implement the task described above.\n"
            "2. Write clean, well-structured code following existing patterns.\n"
            "3. Create a git commit with a descriptive message.\n"
            "4. Create a pull request using `gh pr create`.\n"
            "5. Output the PR URL so it can be tracked.\n"
        )

        cmd = [
            claude_bin,
            "-p", prompt,
            "--output-format", "json",
            "--no-session-persistence",
            "--permission-mode", "dontAsk",
        ]

        logger.info(
            "Running Claude Code for task in %s (timeout=%ds)", repo_path, timeout,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=repo_path,
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
            return (
                f"Error: Claude Code timed out after {timeout}s. "
                "The task may be too large — consider breaking it into smaller pieces."
            )
        except FileNotFoundError:
            return (
                "Error: 'claude' CLI not found. "
                "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
            )

        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace").strip() if stderr else ""
            return (
                f"Error: Claude Code exited with code {proc.returncode}.\n"
                f"stderr: {stderr_text}"
            )

        # Parse JSON output; fall back to raw text
        raw = stdout.decode(errors="replace").strip() if stdout else ""
        try:
            data = json.loads(raw)
            # Claude Code JSON output has a "result" field with the text
            result_text = data.get("result", raw)
            if isinstance(result_text, dict):
                result_text = result_text.get("text", str(result_text))
            return str(result_text)
        except (json.JSONDecodeError, TypeError):
            # Raw text fallback
            return raw if raw else "Claude Code completed but produced no output."

    return run_claude_code  # type: ignore[return-value]
