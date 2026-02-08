"""Agent discovery registry and inter-agent communication tool."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.tools import BaseTool, tool

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
    ``send_message_to_agent`` tool can resolve agent names to URLs at
    runtime.
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


def make_a2a_send_tool(registry: AgentRegistry) -> BaseTool:
    """Create a LangChain tool that sends an A2A message to another agent.

    The returned tool looks up the target agent's URL in *registry* and
    dispatches an A2A ``message/send`` JSON-RPC request via httpx.

    Args:
        registry: The :class:`AgentRegistry` used for agent URL resolution.

    Returns:
        A LangChain :class:`BaseTool` instance.
    """

    @tool
    async def send_message_to_agent(agent_name: str, message: str) -> str:
        """Send a message to another agent via the A2A protocol.

        Args:
            agent_name: The registered name of the target agent (e.g. 'developer').
            message: The message text to send.

        Returns:
            The text response from the target agent, or an error description.
        """
        url = registry.get_agent_url(agent_name)
        if url is None:
            available = [e.definition.metadata.name for e in registry.list_agents()]
            return (
                f"Agent '{agent_name}' not found in registry. "
                f"Available agents: {available}"
            )

        jsonrpc_payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": message}],
                    "messageId": "tool-msg-1",
                },
            },
        }

        logger.info("Sending A2A message to agent '%s' at %s", agent_name, url)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=jsonrpc_payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError:
            logger.exception("HTTP error sending message to agent '%s'", agent_name)
            return f"Failed to communicate with agent '{agent_name}'."

        # Extract response text from the JSON-RPC result
        try:
            result = data.get("result", {})
            # The result may contain artifacts with text parts
            artifacts = result.get("artifacts", [])
            texts: list[str] = []
            for artifact in artifacts:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text" or "text" in part:
                        texts.append(part.get("text", ""))
            if texts:
                return "\n".join(texts)

            # Fallback: try to find text in the result directly
            if "text" in result:
                return result["text"]

            return str(result)
        except Exception:
            logger.exception("Failed to parse response from agent '%s'", agent_name)
            return f"Received unparseable response from agent '{agent_name}'."

    return send_message_to_agent  # type: ignore[return-value]
