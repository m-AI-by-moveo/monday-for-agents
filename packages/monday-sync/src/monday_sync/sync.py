"""Sync agent definitions to the Monday.com registry board."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from a2a_server.agent_loader import load_all_agents
from a2a_server.models import AgentDefinition

from monday_sync import monday_client

logger = logging.getLogger(__name__)


async def _get_existing_agents(board_id: int) -> dict[str, str]:
    """Get existing agent items on the registry board.

    Returns:
        Mapping of agent name -> item ID.
    """
    items = await monday_client.get_board_items(board_id)
    agents: dict[str, str] = {}
    for item in items:
        for col in item.get("column_values", []):
            if col["id"] == "text" and col.get("text"):
                agents[col["text"]] = item["id"]
                break
        else:
            agents[item["name"]] = item["id"]
    return agents


def _build_column_values(agent: AgentDefinition) -> str:
    """Build Monday.com column values JSON from an AgentDefinition."""
    return json.dumps({
        "text": agent.metadata.name,
        "text6": agent.metadata.display_name,
        "text7": agent.metadata.description,
        "numbers": agent.a2a.port,
        "text0": agent.metadata.version,
        "status": {"label": "Active"},
        "text00": ", ".join(agent.metadata.tags),
    })


async def _create_agent_item(board_id: int, agent: AgentDefinition) -> str:
    """Create a new agent item on the registry board."""
    display = agent.metadata.display_name or agent.metadata.name
    query = """
    mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
        create_item(board_id: $boardId, item_name: $itemName, column_values: $columnValues) {
            id
        }
    }
    """
    data = await monday_client.graphql(query, {
        "boardId": str(board_id),
        "itemName": display,
        "columnValues": _build_column_values(agent),
    })
    item_id = data["data"]["create_item"]["id"]
    logger.info("Created agent item: %s (ID: %s)", agent.metadata.name, item_id)
    return item_id


async def _update_agent_item(board_id: int, item_id: str, agent: AgentDefinition) -> None:
    """Update an existing agent item on the registry board."""
    query = """
    mutation ($boardId: ID!, $itemId: ID!, $columnValues: JSON!) {
        change_multiple_column_values(board_id: $boardId, item_id: $itemId, column_values: $columnValues) {
            id
        }
    }
    """
    await monday_client.graphql(query, {
        "boardId": str(board_id),
        "itemId": item_id,
        "columnValues": _build_column_values(agent),
    })
    logger.info("Updated agent item: %s (ID: %s)", agent.metadata.name, item_id)


async def sync_agents(agents_dir: Path, registry_board_id: int) -> None:
    """Sync all agent definitions to the Monday.com registry board.

    Loads agents via a2a-server's ``load_all_agents()``, then creates or
    updates items on the registry board accordingly.
    """
    agents = load_all_agents(agents_dir)
    if not agents:
        logger.warning("No agent definitions found in %s", agents_dir)
        return

    existing = await _get_existing_agents(registry_board_id)
    logger.info("Found %d existing agents on registry board", len(existing))

    for agent in agents:
        name = agent.metadata.name
        if name in existing:
            await _update_agent_item(registry_board_id, existing[name], agent)
        else:
            await _create_agent_item(registry_board_id, agent)

    logger.info("Sync complete: %d agents processed", len(agents))
