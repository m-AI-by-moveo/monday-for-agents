"""Unit tests for a2a_server.agent_executor — A2A / LangGraph bridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_server.agent_executor import LangGraphA2AExecutor, _extract_user_message
from a2a_server.models import AgentDefinition, AgentMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_executor(
    graph: MagicMock | None = None,
    agent_name: str = "test-agent",
) -> LangGraphA2AExecutor:
    """Build an executor with a mock graph and minimal agent definition."""
    mock_graph = graph or MagicMock()
    agent_def = AgentDefinition(metadata=AgentMetadata(name=agent_name))
    return LangGraphA2AExecutor(graph=mock_graph, agent_def=agent_def)


def _make_context(
    text: str = "Hello agent",
    context_id: str = "ctx-123",
    *,
    use_task: bool = False,
) -> SimpleNamespace:
    """Create a fake A2A context carrying a text message.

    The A2A SDK wraps text in a Part > TextPart structure.  We emulate
    that here with SimpleNamespace objects so we do not depend on the
    real SDK types.
    """
    text_part = SimpleNamespace(text=text)
    part = SimpleNamespace(root=text_part)

    if use_task:
        message = SimpleNamespace(parts=[part])
        task = SimpleNamespace(message=message)
        return SimpleNamespace(context_id=context_id, message=None, task=task)

    message = SimpleNamespace(parts=[part])
    return SimpleNamespace(context_id=context_id, message=message, task=None)


def _make_ai_message(content: str) -> SimpleNamespace:
    """Create a fake LangGraph AI message."""
    return SimpleNamespace(type="ai", content=content)


def _make_human_message(content: str) -> SimpleNamespace:
    """Create a fake LangGraph human message."""
    return SimpleNamespace(type="human", content=content)


# ---------------------------------------------------------------------------
# _extract_user_message
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractUserMessage:
    """Tests for the _extract_user_message() helper."""

    def test_extracts_text_from_context_message(self) -> None:
        """Text is extracted from context.message.parts."""
        ctx = _make_context(text="Do something", context_id="ctx-1")
        text, cid = _extract_user_message(ctx)
        assert text == "Do something"
        assert cid == "ctx-1"

    def test_extracts_text_from_context_task(self) -> None:
        """Text is extracted from context.task.message.parts as a fallback."""
        ctx = _make_context(text="Task message", context_id="ctx-2", use_task=True)
        text, cid = _extract_user_message(ctx)
        assert text == "Task message"
        assert cid == "ctx-2"

    def test_uses_context_id(self) -> None:
        """The context_id attribute is propagated."""
        ctx = _make_context(context_id="my-thread")
        _, cid = _extract_user_message(ctx)
        assert cid == "my-thread"

    def test_defaults_context_id_when_missing(self) -> None:
        """When context_id is absent, 'default' is used."""
        ctx = SimpleNamespace(
            message=SimpleNamespace(
                parts=[SimpleNamespace(root=SimpleNamespace(text="hi"))]
            ),
            task=None,
        )
        _, cid = _extract_user_message(ctx)
        assert cid == "default"

    def test_raises_on_empty_message(self) -> None:
        """ValueError is raised when no text can be extracted."""
        ctx = SimpleNamespace(context_id="ctx", message=None, task=None)
        with pytest.raises(ValueError, match="Could not extract"):
            _extract_user_message(ctx)

    def test_joins_multiple_text_parts(self) -> None:
        """Multiple text parts are joined with spaces."""
        part_a = SimpleNamespace(root=SimpleNamespace(text="Hello"))
        part_b = SimpleNamespace(root=SimpleNamespace(text="World"))
        ctx = SimpleNamespace(
            context_id="ctx",
            message=SimpleNamespace(parts=[part_a, part_b]),
            task=None,
        )
        text, _ = _extract_user_message(ctx)
        assert text == "Hello World"


# ---------------------------------------------------------------------------
# LangGraphA2AExecutor.execute – happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteHappyPath:
    """Tests for execute() when the graph invocation succeeds."""

    async def test_invokes_graph_and_returns_response(self) -> None:
        """execute() calls graph.ainvoke and enqueues an artifact."""
        ai_msg = _make_ai_message("Here is my response")
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [_make_human_message("input"), ai_msg]}
        )

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context(text="Hello", context_id="thread-1")
        await executor.execute(ctx, event_queue)

        mock_graph.ainvoke.assert_awaited_once()
        call_args = mock_graph.ainvoke.call_args
        assert call_args[0][0] == {"messages": [("user", "Hello")]}
        assert call_args[1]["config"]["configurable"]["thread_id"] == "thread-1"

        event_queue.enqueue_event.assert_awaited_once()
        artifact = event_queue.enqueue_event.call_args[0][0]
        assert artifact.name == "response"

    async def test_uses_context_id_as_thread_id(self) -> None:
        """The A2A context_id is forwarded as the LangGraph thread_id."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [_make_ai_message("ok")]}
        )

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context(context_id="custom-thread-42")
        await executor.execute(ctx, event_queue)

        config = mock_graph.ainvoke.call_args[1]["config"]
        assert config["configurable"]["thread_id"] == "custom-thread-42"

    async def test_emits_artifact_via_event_queue(self) -> None:
        """execute() sends an Artifact with the AI response text."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [_make_ai_message("Detailed answer")]}
        )

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context()
        await executor.execute(ctx, event_queue)

        artifact = event_queue.enqueue_event.call_args[0][0]
        # The artifact has parts; the first text part should contain the AI text
        text_content = artifact.parts[0].root.text
        assert text_content == "Detailed answer"

    async def test_handles_no_ai_message_in_result(self) -> None:
        """When the graph returns no AI message, a fallback is emitted."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={"messages": [_make_human_message("user said this")]}
        )

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context()
        await executor.execute(ctx, event_queue)

        artifact = event_queue.enqueue_event.call_args[0][0]
        assert "did not produce a response" in artifact.parts[0].root.text

    async def test_handles_empty_messages_list(self) -> None:
        """When the graph returns an empty messages list, a fallback is emitted."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(return_value={"messages": []})

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context()
        await executor.execute(ctx, event_queue)

        artifact = event_queue.enqueue_event.call_args[0][0]
        assert "did not produce a response" in artifact.parts[0].root.text


# ---------------------------------------------------------------------------
# LangGraphA2AExecutor.execute – error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteErrorHandling:
    """Tests for execute() error paths."""

    async def test_handles_graph_invocation_error(self) -> None:
        """When graph.ainvoke raises, an error artifact is enqueued."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM broke"))

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context()
        await executor.execute(ctx, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        artifact = event_queue.enqueue_event.call_args[0][0]
        assert artifact.name == "error"
        assert "internal error" in artifact.parts[0].root.text.lower()

    async def test_handles_unparseable_context(self) -> None:
        """When the context has no extractable message, an error artifact is sent."""
        executor = _make_executor()
        event_queue = AsyncMock()

        ctx = SimpleNamespace(context_id="ctx", message=None, task=None)
        await executor.execute(ctx, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        artifact = event_queue.enqueue_event.call_args[0][0]
        assert artifact.name == "error"
        assert "parse" in artifact.parts[0].root.text.lower()

    async def test_does_not_raise_on_graph_error(self) -> None:
        """execute() swallows exceptions and does not let them propagate."""
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(side_effect=Exception("catastrophic"))

        executor = _make_executor(graph=mock_graph)
        event_queue = AsyncMock()

        ctx = _make_context()
        # Should NOT raise
        await executor.execute(ctx, event_queue)
