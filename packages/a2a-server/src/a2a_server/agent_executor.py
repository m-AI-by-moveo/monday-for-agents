"""Bridge between the A2A SDK AgentExecutor interface and LangGraph."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.server.agent_execution.context import RequestContext
from langgraph.graph.state import CompiledStateGraph

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
    task: Task | None = context.current_task
    if task is not None:
        task_message: Message | None = getattr(task, "message", None)
        if task_message is not None:
            parts = task_message.parts or []
            text_parts = [
                p.root.text for p in parts
                if isinstance(getattr(p, "root", p), TextPart)
            ]
            if text_parts:
                return " ".join(text_parts), context_id

    raise ValueError("Could not extract user message text from A2A context")


class LangGraphA2AExecutor(AgentExecutor):
    """Runs a LangGraph agent in response to A2A requests.

    Each incoming A2A message is forwarded to the compiled LangGraph as a
    ``("user", text)`` message.  The LangGraph checkpointer uses the A2A
    ``context_id`` as the ``thread_id`` so that multi-turn conversations
    are preserved.
    """

    def __init__(self, graph: CompiledStateGraph, agent_def: AgentDefinition) -> None:
        self.graph = graph
        self.agent_def = agent_def

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Execute a single A2A request by invoking the LangGraph agent."""
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
            agent_name,
            context_id,
            cid or "none",
            message_text,
        )

        # Signal that the agent is working
        await event_queue.enqueue_event(
            self._make_status_event(context, TaskState.working),
        )

        try:
            result = await self.graph.ainvoke(
                {"messages": [("user", message_text)]},
                config={"configurable": {"thread_id": context_id}},
            )

            # The result contains a "messages" list; the last AI message
            # is the agent's response.
            messages = result.get("messages", [])
            ai_content = ""
            for msg in reversed(messages):
                if getattr(msg, "type", None) == "ai" and getattr(msg, "content", None):
                    ai_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    break

            if not ai_content:
                ai_content = "Agent did not produce a response."

            logger.info(
                "Agent '%s' response (context=%s, correlation=%s): %.120s...",
                agent_name,
                context_id,
                cid or "none",
                ai_content,
            )

            # Emit completed status with the response message
            await event_queue.enqueue_event(
                self._make_status_event(
                    context, TaskState.completed, ai_content,
                ),
            )

        except Exception:
            logger.exception("Agent '%s' failed during graph execution", agent_name)
            await event_queue.enqueue_event(
                self._make_status_event(
                    context, TaskState.failed,
                    "An internal error occurred while processing your request.",
                ),
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """Cancel a running task."""
        await event_queue.enqueue_event(
            self._make_status_event(context, TaskState.canceled),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
