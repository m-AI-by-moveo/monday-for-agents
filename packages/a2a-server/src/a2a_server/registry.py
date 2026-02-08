"""Agent discovery registry for A2A agent URL resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from a2a_server.models import AgentDefinition

logger = logging.getLogger(__name__)


@dataclass
class AgentEntry:
    """A registered agent with its definition and runtime URL."""

    definition: AgentDefinition
    url: str


class AgentRegistry:
    """In-memory registry mapping agent names to their A2A endpoints.

    This is used at startup to register all known agents so that the
    MCP bridge server can resolve agent names to URLs at runtime.
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentEntry] = {}

    def register(self, agent_def: AgentDefinition) -> None:
        """Register an agent definition.

        The A2A URL is derived from the agent's configured port.
        """
        url = f"http://localhost:{agent_def.a2a.port}"
        self._agents[agent_def.metadata.name] = AgentEntry(
            definition=agent_def,
            url=url,
        )
        logger.info(
            "Registered agent '%s' at %s",
            agent_def.metadata.name,
            url,
        )

    def get_agent_url(self, name: str) -> str | None:
        """Return the A2A URL for *name*, or ``None`` if not registered."""
        entry = self._agents.get(name)
        return entry.url if entry else None

    def list_agents(self) -> list[AgentEntry]:
        """Return all registered agent entries."""
        return list(self._agents.values())

    @classmethod
    def from_definitions(cls, definitions: list[AgentDefinition]) -> AgentRegistry:
        """Create a registry pre-populated with a list of definitions."""
        registry = cls()
        for defn in definitions:
            registry.register(defn)
        return registry
