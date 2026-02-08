"""Bridge between the A2A SDK AgentExecutor interface and LangGraph."""

from __future__ import annotations

import logging
from typing import Any

from a2a.server.agent_executor import AgentExecutor
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    Message,
    Part,
    Task,
    TaskState,
    TextPart,
)
from langgraph.graph.graph import CompiledGraph

from a2a_server.models import AgentDefinition

logger = logging.getLogger(__name__)


def _extract_user_message(context: Any) -> tuple[str, str]:
    """Extract user message text and context ID from an A2A execution context.

    The A2A SDK provides context with either a ``message`` or ``task``
    attribute.  This helper normalises both cases.

    Returns:
        A ``(message_text, context_id)`` tuple.
    """
    context_id = getattr(context, "context_id", None) or "default"

    # Try to get message from context.message first, then context.task
    message: Message | None = getattr(context, "message", None)
    task: Task | None = getattr(context, "task", None)

    if message is not None:
        parts = message.parts or []
        text_parts = [
            p.root.text for p in parts
            if isinstance(getattr(p, "root", p), TextPart)
        ]
        if text_parts:
            return " ".join(text_parts), context_id

        # Fallback: check for a plain text attribute
        text = getattr(message, "text", None)
        if text:
            return str(text), context_id

    if task is not None:
        # Tasks may carry the original message
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

    def __init__(self, graph: CompiledGraph, agent_def: AgentDefinition) -> None:
        self.graph = graph
        self.agent_def = agent_def

    async def execute(
        self,
        context: Any,
        event_queue: EventQueue,
    ) -> None:
        """Execute a single A2A request by invoking the LangGraph agent.

        Args:
            context: The A2A execution context carrying the inbound message.
            event_queue: Queue used to emit response events back to the
                A2A caller.
        """
        agent_name = self.agent_def.metadata.name

        try:
            message_text, context_id = _extract_user_message(context)
        except ValueError:
            logger.exception("Failed to extract message for agent '%s'", agent_name)
            await event_queue.enqueue_event(
                self._make_error_artifact("Unable to parse the incoming message."),
            )
            return

        logger.info(
            "Agent '%s' received message (context=%s): %.120s...",
            agent_name,
            context_id,
            message_text,
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
                "Agent '%s' response (context=%s): %.120s...",
                agent_name,
                context_id,
                ai_content,
            )

            artifact = Artifact(
                parts=[Part(root=TextPart(text=ai_content))],
                name="response",
            )
            await event_queue.enqueue_event(artifact)

        except Exception:
            logger.exception("Agent '%s' failed during graph execution", agent_name)
            await event_queue.enqueue_event(
                self._make_error_artifact(
                    "An internal error occurred while processing your request."
                ),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_error_artifact(text: str) -> Artifact:
        return Artifact(
            parts=[Part(root=TextPart(text=text))],
            name="error",
        )
