"""Create a Starlette-based A2A application from an agent definition."""

from __future__ import annotations

import logging

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import (
    DefaultRequestHandler,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from a2a_server.models import AgentDefinition

logger = logging.getLogger(__name__)


def _build_agent_card(agent_def: AgentDefinition) -> AgentCard:
    """Translate an :class:`AgentDefinition` into an A2A :class:`AgentCard`.

    The resulting card is served at ``/.well-known/agent.json`` by the
    A2A Starlette application.
    """
    skills = [
        AgentSkill(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            tags=[],
            examples=[],
        )
        for skill in agent_def.a2a.skills
    ]

    capabilities = AgentCapabilities(
        streaming=agent_def.a2a.capabilities.streaming,
    )

    url = f"http://localhost:{agent_def.a2a.port}"

    card = AgentCard(
        name=agent_def.metadata.display_name or agent_def.metadata.name,
        description=agent_def.metadata.description,
        url=url,
        version=agent_def.metadata.version,
        skills=skills,
        capabilities=capabilities,
        default_input_modes=["text"],
        default_output_modes=["text"],
    )

    logger.info(
        "Built AgentCard for '%s' at %s with %d skill(s)",
        card.name,
        url,
        len(skills),
    )
    return card


def create_a2a_app(
    agent_def: AgentDefinition,
    executor: AgentExecutor,
) -> A2AStarletteApplication:
    """Create an A2A Starlette application for the given agent.

    Args:
        agent_def: The parsed agent definition providing metadata and skills.
        executor: The :class:`AgentExecutor` implementation that handles
            incoming A2A requests.

    Returns:
        A :class:`A2AStarletteApplication` ready to be served by uvicorn.
    """
    card = _build_agent_card(agent_def)

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        queue_manager=InMemoryQueueManager(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )
    logger.info("A2A application created for agent '%s'", agent_def.metadata.name)
    return app
