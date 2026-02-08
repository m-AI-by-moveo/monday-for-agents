"""Unit tests for a2a_server.claude_code_executor — Claude Code CLI executor."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from a2a.types import Message, Part, TextPart

from a2a_server.claude_code_executor import ClaudeCodeExecutor, _extract_user_message
from a2a_server.models import (
    AgentDefinition,
    AgentMetadata,
    ClaudeCodeConfig,
    LLMConfig,
    PromptConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_def(
    name: str = "test-agent",
    timeout: int = 60,
    allowed_tools: list[str] | None = None,
    system_prompt: str = "You are a test agent.",
    model: str = "anthropic/claude-sonnet-4-20250514",
) -> AgentDefinition:
    """Build a minimal AgentDefinition for testing."""
    return AgentDefinition(
        metadata=AgentMetadata(name=name),
        llm=LLMConfig(model=model),
        claude_code=ClaudeCodeConfig(
            timeout=timeout,
            allowed_tools=allowed_tools or [],
        ),
        prompt=PromptConfig(system=system_prompt),
    )


def _make_executor(
    agent_def: AgentDefinition | None = None,
    mcp_config: dict | None = None,
) -> ClaudeCodeExecutor:
    """Build an executor with optional overrides."""
    return ClaudeCodeExecutor(
        agent_def=agent_def or _make_agent_def(),
        mcp_config=mcp_config or {"mcpServers": {}},
    )


def _make_context(
    text: str = "Hello agent",
    context_id: str = "ctx-123",
    task_id: str = "task-1",
    *,
    use_task: bool = False,
) -> SimpleNamespace:
    """Create a fake A2A context using real A2A Part/TextPart types."""
    part = Part(root=TextPart(text=text))

    if use_task:
        task_msg = Message(
            role="user", parts=[part], message_id="test-msg",
        )
        task = SimpleNamespace(message=task_msg)
        return SimpleNamespace(
            context_id=context_id, task_id=task_id,
            message=None, current_task=task,
        )

    message = Message(role="user", parts=[part], message_id="test-msg")
    return SimpleNamespace(
        context_id=context_id, task_id=task_id,
        message=message, current_task=None,
    )


# ---------------------------------------------------------------------------
# _extract_user_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractUserMessage:
    """Tests for the _extract_user_message() helper."""

    def test_extracts_text_from_context_message(self) -> None:
        ctx = _make_context(text="Do something", context_id="ctx-1")
        text, cid = _extract_user_message(ctx)
        assert text == "Do something"
        assert cid == "ctx-1"

    def test_extracts_text_from_context_task(self) -> None:
        ctx = _make_context(text="Task message", context_id="ctx-2", use_task=True)
        text, cid = _extract_user_message(ctx)
        assert text == "Task message"
        assert cid == "ctx-2"

    def test_defaults_context_id_when_missing(self) -> None:
        part = Part(root=TextPart(text="hi"))
        ctx = SimpleNamespace(
            context_id=None, task_id="t1",
            message=Message(role="user", parts=[part], message_id="m1"),
            current_task=None,
        )
        _, cid = _extract_user_message(ctx)
        assert cid == "default"

    def test_raises_on_empty_message(self) -> None:
        ctx = SimpleNamespace(
            context_id="ctx", task_id="t1",
            message=None, current_task=None,
        )
        with pytest.raises(ValueError, match="Could not extract"):
            _extract_user_message(ctx)

    def test_joins_multiple_text_parts(self) -> None:
        part_a = Part(root=TextPart(text="Hello"))
        part_b = Part(root=TextPart(text="World"))
        ctx = SimpleNamespace(
            context_id="ctx", task_id="t1",
            message=Message(role="user", parts=[part_a, part_b], message_id="m1"),
            current_task=None,
        )
        text, _ = _extract_user_message(ctx)
        assert text == "Hello World"


# ---------------------------------------------------------------------------
# ClaudeCodeExecutor.execute — happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteHappyPath:
    """Tests for execute() when claude -p succeeds."""

    async def test_successful_execution_emits_completed(self) -> None:
        """Successful claude -p run emits a completed status event."""
        executor = _make_executor()
        event_queue = AsyncMock()
        ctx = _make_context(text="Build a feature")

        json_output = json.dumps({"result": "Feature built successfully"})

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(json_output.encode(), b""),
        )
        mock_proc.returncode = 0

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            await executor.execute(ctx, event_queue)

        # Should have emitted at least working + completed events
        assert event_queue.enqueue_event.await_count >= 2
        last_event = event_queue.enqueue_event.call_args_list[-1][0][0]
        assert last_event.status.state.value == "completed"
        assert "Feature built" in last_event.status.message.parts[0].root.text

    async def test_passes_system_prompt_flag(self) -> None:
        """The system prompt is passed via --system-prompt flag."""
        agent_def = _make_agent_def(system_prompt="Be helpful")
        executor = _make_executor(agent_def=agent_def)
        event_queue = AsyncMock()
        ctx = _make_context()

        captured_cmd = []

        async def mock_create_subprocess(*args, **kwargs):
            captured_cmd.extend(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(b'{"result": "ok"}', b""),
            )
            proc.returncode = 0
            return proc

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", side_effect=mock_create_subprocess),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            await executor.execute(ctx, event_queue)

        cmd = captured_cmd
        assert "--system-prompt" in cmd
        idx = cmd.index("--system-prompt")
        assert cmd[idx + 1] == "Be helpful"

    async def test_passes_allowed_tools(self) -> None:
        """Allowed tools are passed via --allowedTools flags."""
        agent_def = _make_agent_def(
            allowed_tools=["mcp__monday__*", "mcp__a2a-bridge__*"],
        )
        executor = _make_executor(agent_def=agent_def)
        event_queue = AsyncMock()
        ctx = _make_context()

        captured_cmd = []

        async def mock_create_subprocess(*args, **kwargs):
            captured_cmd.extend(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(b'{"result": "ok"}', b""),
            )
            proc.returncode = 0
            return proc

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", side_effect=mock_create_subprocess),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            await executor.execute(ctx, event_queue)

        cmd = captured_cmd
        indices = [i for i, x in enumerate(cmd) if x == "--allowedTools"]
        assert len(indices) == 2
        tools = [cmd[i + 1] for i in indices]
        assert "mcp__monday__*" in tools
        assert "mcp__a2a-bridge__*" in tools

    async def test_strips_anthropic_prefix_from_model(self) -> None:
        """The anthropic/ prefix is stripped from the model for --model flag."""
        agent_def = _make_agent_def(model="anthropic/claude-sonnet-4-20250514")
        executor = _make_executor(agent_def=agent_def)
        event_queue = AsyncMock()
        ctx = _make_context()

        captured_cmd = []

        async def mock_create_subprocess(*args, **kwargs):
            captured_cmd.extend(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(
                return_value=(b'{"result": "ok"}', b""),
            )
            proc.returncode = 0
            return proc

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", side_effect=mock_create_subprocess),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            await executor.execute(ctx, event_queue)

        cmd = captured_cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# ClaudeCodeExecutor.execute — error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteErrorHandling:
    """Tests for execute() error paths."""

    async def test_missing_claude_binary_emits_failed(self) -> None:
        """When claude binary is not found, a failed event is emitted."""
        executor = _make_executor()
        event_queue = AsyncMock()
        ctx = _make_context()

        with patch("a2a_server.claude_code_executor.shutil.which", return_value=None):
            await executor.execute(ctx, event_queue)

        last_event = event_queue.enqueue_event.call_args_list[-1][0][0]
        assert last_event.status.state.value == "failed"
        assert "not found" in last_event.status.message.parts[0].root.text.lower()

    async def test_unparseable_context_emits_failed(self) -> None:
        """When context has no message, a failed event is emitted."""
        executor = _make_executor()
        event_queue = AsyncMock()
        ctx = SimpleNamespace(
            context_id="ctx", task_id="t1",
            message=None, current_task=None,
        )

        await executor.execute(ctx, event_queue)

        last_event = event_queue.enqueue_event.call_args_list[-1][0][0]
        assert last_event.status.state.value == "failed"
        assert "parse" in last_event.status.message.parts[0].root.text.lower()

    async def test_timeout_emits_failed(self) -> None:
        """When subprocess times out, a failed event is emitted."""
        agent_def = _make_agent_def(timeout=1)
        executor = _make_executor(agent_def=agent_def)
        event_queue = AsyncMock()
        ctx = _make_context()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", side_effect=asyncio.TimeoutError()),
        ):
            await executor.execute(ctx, event_queue)

        last_event = event_queue.enqueue_event.call_args_list[-1][0][0]
        assert last_event.status.state.value == "failed"
        assert "timed out" in last_event.status.message.parts[0].root.text.lower()

    async def test_nonzero_exit_returns_error_text(self) -> None:
        """Non-zero exit code returns error text in completed event."""
        executor = _make_executor()
        event_queue = AsyncMock()
        ctx = _make_context()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"fatal error occurred"),
        )
        mock_proc.returncode = 1

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            await executor.execute(ctx, event_queue)

        last_event = event_queue.enqueue_event.call_args_list[-1][0][0]
        # Non-zero exit is returned as completed with error text (not failed)
        assert last_event.status.state.value == "completed"
        assert "error" in last_event.status.message.parts[0].root.text.lower()

    async def test_json_parse_fallback_to_raw_text(self) -> None:
        """When JSON parsing fails, raw text is returned."""
        executor = _make_executor()
        event_queue = AsyncMock()
        ctx = _make_context()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"This is raw text output", b""),
        )
        mock_proc.returncode = 0

        with (
            patch("a2a_server.claude_code_executor.shutil.which", return_value="/usr/bin/claude"),
            patch("a2a_server.claude_code_executor.asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("a2a_server.claude_code_executor.asyncio.wait_for", new=_passthrough_wait_for),
        ):
            await executor.execute(ctx, event_queue)

        last_event = event_queue.enqueue_event.call_args_list[-1][0][0]
        assert last_event.status.state.value == "completed"
        assert "raw text output" in last_event.status.message.parts[0].root.text


# ---------------------------------------------------------------------------
# ClaudeCodeExecutor.cancel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCancel:
    """Tests for cancel()."""

    async def test_cancel_emits_canceled_event(self) -> None:
        executor = _make_executor()
        event_queue = AsyncMock()
        ctx = _make_context()

        await executor.cancel(ctx, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        event = event_queue.enqueue_event.call_args[0][0]
        assert event.status.state.value == "canceled"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _passthrough_wait_for(coro, timeout):
    """Pass-through wait_for that doesn't enforce a timeout."""
    return await coro
