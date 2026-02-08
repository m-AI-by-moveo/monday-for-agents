"""Lightweight FastMCP server bridging Claude Code agents to other A2A agents.

This server runs as an MCP stdio transport, launched by Claude Code via
``--mcp-config``.  It reads the agent registry from the ``MFA_AGENT_REGISTRY``
environment variable (a JSON dict of ``{name: url}``) and exposes two tools:

- ``send_message_to_agent`` -- POSTs a JSON-RPC ``message/send`` to a target agent
- ``list_available_agents`` -- returns the registry contents for discovery
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("a2a-bridge")

# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, str]:
    """Load agent name -> URL mapping from MFA_AGENT_REGISTRY env var."""
    raw = os.environ.get("MFA_AGENT_REGISTRY", "{}")
    try:
        registry = json.loads(raw)
        if not isinstance(registry, dict):
            logger.error("MFA_AGENT_REGISTRY is not a JSON object: %s", raw)
            return {}
        return registry
    except json.JSONDecodeError:
        logger.exception("Failed to parse MFA_AGENT_REGISTRY: %s", raw)
        return {}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def send_message_to_agent(agent_name: str, message: str) -> str:
    """Send a message to another agent via the A2A protocol.

    Args:
        agent_name: The registered name of the target agent (e.g. 'developer').
        message: The message text to send.

    Returns:
        The text response from the target agent, or an error description.
    """
    registry = _load_registry()
    url = registry.get(agent_name)
    if url is None:
        available = list(registry.keys())
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
                "messageId": "bridge-msg-1",
            },
        },
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = os.environ.get("MFA_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key

    logger.info("Sending A2A message to agent '%s' at %s", agent_name, url)

    max_retries = 2
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url, json=jsonrpc_payload, headers=headers,
                )
                response.raise_for_status()
                data = response.json()

            # Extract response text from JSON-RPC result
            result = data.get("result", {})
            status = result.get("status", {})
            status_message = status.get("message", {})

            # Try status.message.parts first (standard A2A response)
            parts = status_message.get("parts", [])
            texts: list[str] = []
            for part in parts:
                if part.get("kind") == "text" or "text" in part:
                    texts.append(part.get("text", ""))
            if texts:
                return "\n".join(texts)

            # Try artifacts
            artifacts = result.get("artifacts", [])
            for artifact in artifacts:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text" or "text" in part:
                        texts.append(part.get("text", ""))
            if texts:
                return "\n".join(texts)

            return str(result)

        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < max_retries:
                logger.warning(
                    "Attempt %d/%d to '%s' failed: %s",
                    attempt + 1, max_retries + 1, agent_name, exc,
                )
                continue
        except Exception as exc:
            last_error = exc
            break

    logger.error("Failed to communicate with agent '%s': %s", agent_name, last_error)
    return f"Failed to communicate with agent '{agent_name}': {last_error}"


@mcp.tool()
async def list_available_agents() -> str:
    """List all agents available in the registry.

    Returns:
        A JSON string with agent names and their A2A URLs.
    """
    registry = _load_registry()
    if not registry:
        return "No agents registered. Check MFA_AGENT_REGISTRY environment variable."
    return json.dumps(registry, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the A2A bridge MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
