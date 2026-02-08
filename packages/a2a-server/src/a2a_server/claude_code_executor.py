"""AgentExecutor that spawns Claude Code CLI (``claude -p``) as the agent brain."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    Message,
    Part,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.server.agent_execution.context import RequestContext

from a2a_server.models import AgentDefinition
from a2a_server.tracing import get_correlation_id

logger = logging.getLogger(__name__)


def _extract_user_message(context: RequestContext) -> tuple[str, str]:
    """Extract user message text and context ID from an A2A RequestContext.

    Returns:
        A ``(message_text, context_id)`` tuple.
    """
    context_id = context.context_id or "default"

    message: Message | None = context.message
    if message is not None:
        parts = message.parts or []
        text_parts = [
            p.root.text for p in parts
            if isinstance(getattr(p, "root", p), TextPart)
        ]
        if text_parts:
            return " ".join(text_parts), context_id

    # Try from current_task
    task = context.current_task
    if task is not None:
        task_message = getattr(task, "message", None)
        if task_message is not None:
            parts = task_message.parts or []
            text_parts = [
                p.root.text for p in parts
                if isinstance(getattr(p, "root", p), TextPart)
            ]
            if text_parts:
                return " ".join(text_parts), context_id

    raise ValueError("Could not extract user message text from A2A context")


class ClaudeCodeExecutor(AgentExecutor):
    """Runs Claude Code CLI as the agent brain via ``claude -p`` subprocess.

    Each incoming A2A message is forwarded to the ``claude`` CLI as a
    prompt.  MCP tools and system prompt are provided via flags.  All
    LLM usage goes through the Claude Code subscription (Pro Max).
    """

    def __init__(
        self,
        agent_def: AgentDefinition,
        mcp_config: dict[str, Any],
    ) -> None:
        self.agent_def = agent_def
        self.mcp_config = mcp_config

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a single A2A request by invoking claude -p."""
        agent_name = self.agent_def.metadata.name

        try:
            message_text, context_id = _extract_user_message(context)
        except ValueError:
            logger.exception("Failed to extract message for agent '%s'", agent_name)
            await event_queue.enqueue_event(
                self._make_status_event(
                    context, TaskState.failed,
                    "Unable to parse the incoming message.",
                ),
            )
            return

        cid = get_correlation_id()
        logger.info(
            "Agent '%s' received message (context=%s, correlation=%s): %.120s...",
            agent_name, context_id, cid or "none", message_text,
        )

        # Signal that the agent is working
        await event_queue.enqueue_event(
            self._make_status_event(context, TaskState.working),
        )

        # Verify claude binary
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            logger.error("'claude' CLI not found on PATH")
            await event_queue.enqueue_event(
                self._make_status_event(
                    context, TaskState.failed,
                    "Claude Code CLI not found. Install: https://docs.anthropic.com/en/docs/claude-code",
                ),
            )
            return

        # Write MCP config to temp file
        mcp_config_file = None
        try:
            mcp_config_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix="mcp-config-", delete=False,
            )
            json.dump(self.mcp_config, mcp_config_file)
            mcp_config_file.close()

            result_text = await self._run_claude(
                claude_bin, message_text, mcp_config_file.name, context_id,
            )

            logger.info(
                "Agent '%s' response (context=%s): %.120s...",
                agent_name, context_id, result_text,
            )

            await event_queue.enqueue_event(
                self._make_status_event(context, TaskState.completed, result_text),
            )

        except asyncio.TimeoutError:
            logger.error(
                "Agent '%s' timed out after %ds",
                agent_name, self.agent_def.claude_code.timeout,
            )
            await event_queue.enqueue_event(
                self._make_status_event(
                    context, TaskState.failed,
                    f"Agent timed out after {self.agent_def.claude_code.timeout}s.",
                ),
            )
        except Exception:
            logger.exception("Agent '%s' failed during execution", agent_name)
            await event_queue.enqueue_event(
                self._make_status_event(
                    context, TaskState.failed,
                    "An internal error occurred while processing your request.",
                ),
            )
        finally:
            if mcp_config_file is not None:
                try:
                    Path(mcp_config_file.name).unlink(missing_ok=True)
                except OSError:
                    pass

    async def _run_claude(
        self,
        claude_bin: str,
        message: str,
        mcp_config_path: str,
        context_id: str,
    ) -> str:
        """Spawn ``claude -p`` and return the result text."""
        agent_def = self.agent_def
        cc_config = agent_def.claude_code

        # Extract model name (strip anthropic/ prefix if present)
        model = agent_def.llm.model
        if model.startswith("anthropic/"):
            model = model.removeprefix("anthropic/")

        cmd: list[str] = [
            claude_bin,
            "-p", message,
            "--output-format", "json",
            "--permission-mode", "dontAsk",
            "--no-session-persistence",
            "--model", model,
        ]

        # System prompt — interpolate {board_id} with actual Monday board ID
        system_prompt = agent_def.prompt.system
        if system_prompt:
            board_id = agent_def.monday.board_id if agent_def.monday else ""
            if board_id:
                system_prompt = system_prompt.replace("{board_id}", board_id)
                logger.info("Interpolated {board_id} → %s in system prompt", board_id)
            else:
                logger.warning("No board_id available for prompt interpolation")
            cmd.extend(["--system-prompt", system_prompt])

        # MCP config
        cmd.extend(["--mcp-config", mcp_config_path])

        # Allowed tools
        if cc_config.allowed_tools:
            for tool_pattern in cc_config.allowed_tools:
                cmd.extend(["--allowedTools", tool_pattern])

        # Additional directories
        for add_dir in cc_config.add_dirs:
            cmd.extend(["--add-dir", add_dir])

        timeout = cc_config.timeout

        logger.info(
            "Spawning claude -p for agent '%s' (timeout=%ds, model=%s)",
            agent_def.metadata.name, timeout, model,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        if proc.returncode != 0:
            stderr_text = stderr.decode(errors="replace").strip() if stderr else ""
            logger.error(
                "claude -p exited with code %d for agent '%s': %s",
                proc.returncode, agent_def.metadata.name, stderr_text,
            )
            return f"Claude Code error (exit {proc.returncode}): {stderr_text}"

        # Parse JSON output
        raw = stdout.decode(errors="replace").strip() if stdout else ""
        try:
            data = json.loads(raw)
            result_text = data.get("result", raw)
            if isinstance(result_text, dict):
                result_text = result_text.get("text", str(result_text))
            return str(result_text)
        except (json.JSONDecodeError, TypeError):
            return raw if raw else "Agent completed but produced no output."

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Cancel a running task."""
        await event_queue.enqueue_event(
            self._make_status_event(context, TaskState.canceled),
        )

    @staticmethod
    def _make_status_event(
        context: RequestContext,
        state: TaskState,
        text: str | None = None,
    ) -> TaskStatusUpdateEvent:
        message = None
        if text:
            message = Message(
                role="agent",
                parts=[Part(root=TextPart(text=text))],
                message_id=str(uuid.uuid4()),
            )
        return TaskStatusUpdateEvent(
            task_id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=state, message=message),
            final=state in (TaskState.completed, TaskState.failed, TaskState.canceled),
        )
