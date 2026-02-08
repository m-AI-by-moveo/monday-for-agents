"""Sync agent YAML definitions to Monday.com registry board."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import click
import httpx
import yaml

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"


def _get_headers() -> dict[str, str]:
    token = os.environ.get("MONDAY_API_TOKEN")
    if not token:
        raise ValueError("MONDAY_API_TOKEN environment variable is required")
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }


def _load_agent_yaml(path: Path) -> dict:
    """Load and parse an agent YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


async def _get_existing_agents(board_id: int) -> dict[str, str]:
    """Get existing agent items on the registry board.

    Returns:
        Mapping of agent name → item ID.
    """
    query = """
    query ($boardId: [ID!]!) {
        boards(ids: $boardId) {
            items_page(limit: 100) {
                items {
                    id
                    name
                    column_values {
                        id
                        text
                    }
                }
            }
        }
    }
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MONDAY_API_URL,
            json={"query": query, "variables": {"boardId": [str(board_id)]}},
            headers=_get_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    agents = {}
    boards = data.get("data", {}).get("boards", [])
    if boards:
        items = boards[0].get("items_page", {}).get("items", [])
        for item in items:
            # Find the agent_name column
            for col in item.get("column_values", []):
                if col["id"] == "text" and col.get("text"):
                    agents[col["text"]] = item["id"]
                    break
            else:
                agents[item["name"]] = item["id"]

    return agents


async def _create_agent_item(board_id: int, agent_data: dict) -> str:
    """Create a new agent item on the registry board."""
    metadata = agent_data.get("metadata", {})
    a2a_config = agent_data.get("a2a", {})

    column_values = json.dumps({
        "text": metadata.get("name", ""),
        "text6": metadata.get("display_name", ""),
        "text7": metadata.get("description", ""),
        "numbers": a2a_config.get("port", 0),
        "text0": metadata.get("version", "1.0.0"),
        "status": {"label": "Active"},
        "text00": ", ".join(metadata.get("tags", [])),
    })

    query = """
    mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
        create_item(board_id: $boardId, item_name: $itemName, column_values: $columnValues) {
            id
        }
    }
    """
    variables = {
        "boardId": str(board_id),
        "itemName": metadata.get("display_name", metadata.get("name", "Unknown")),
        "columnValues": column_values,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=_get_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Failed to create agent item: {data['errors']}")

    item_id = data["data"]["create_item"]["id"]
    logger.info("Created agent item: %s (ID: %s)", metadata.get("name"), item_id)
    return item_id


async def _update_agent_item(board_id: int, item_id: str, agent_data: dict) -> None:
    """Update an existing agent item on the registry board."""
    metadata = agent_data.get("metadata", {})
    a2a_config = agent_data.get("a2a", {})

    column_values = json.dumps({
        "text": metadata.get("name", ""),
        "text6": metadata.get("display_name", ""),
        "text7": metadata.get("description", ""),
        "numbers": a2a_config.get("port", 0),
        "text0": metadata.get("version", "1.0.0"),
        "status": {"label": "Active"},
        "text00": ", ".join(metadata.get("tags", [])),
    })

    query = """
    mutation ($boardId: ID!, $itemId: ID!, $columnValues: JSON!) {
        change_multiple_column_values(board_id: $boardId, item_id: $itemId, column_values: $columnValues) {
            id
        }
    }
    """
    variables = {
        "boardId": str(board_id),
        "itemId": item_id,
        "columnValues": column_values,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=_get_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Failed to update agent item: {data['errors']}")

    logger.info("Updated agent item: %s (ID: %s)", metadata.get("name"), item_id)


async def sync_agents(agents_dir: Path, registry_board_id: int) -> None:
    """Sync all agent YAML definitions to the Monday.com registry board.

    Creates new items for new agents, updates existing items for known agents.
    """
    # Load all agent YAML files
    yaml_files = sorted(agents_dir.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No agent YAML files found in %s", agents_dir)
        return

    agent_definitions = []
    for path in yaml_files:
        try:
            data = _load_agent_yaml(path)
            agent_definitions.append(data)
            logger.info("Loaded agent definition: %s", path.name)
        except Exception as e:
            logger.error("Failed to load %s: %s", path.name, e)

    # Get existing agents on the board
    existing = await _get_existing_agents(registry_board_id)
    logger.info("Found %d existing agents on registry board", len(existing))

    # Sync each agent
    for agent_data in agent_definitions:
        name = agent_data.get("metadata", {}).get("name", "unknown")
        if name in existing:
            await _update_agent_item(registry_board_id, existing[name], agent_data)
        else:
            await _create_agent_item(registry_board_id, agent_data)

    logger.info("Sync complete: %d agents processed", len(agent_definitions))


@click.group()
def cli():
    """Monday.com agent sync tools."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.command()
@click.option(
    "--agents-dir",
    type=click.Path(exists=True, path_type=Path),
    default=Path(__file__).parent.parent.parent.parent.parent / "agents",
    help="Path to agents YAML directory",
)
@click.option(
    "--board-id",
    type=int,
    envvar="MONDAY_REGISTRY_BOARD_ID",
    required=True,
    help="Monday.com registry board ID",
)
def sync(agents_dir: Path, board_id: int):
    """Sync agent YAML definitions to Monday.com registry board."""
    asyncio.run(sync_agents(agents_dir, board_id))


@cli.command()
@click.option("--workspace-id", type=int, default=None, help="Monday.com workspace ID")
def setup(workspace_id: int | None):
    """Create Monday.com boards (Tasks + Registry) with correct schema."""
    from monday_sync.board_setup import create_tasks_board, setup_registry_board

    async def _setup():
        tasks_board = await create_tasks_board(workspace_id)
        registry_board = await setup_registry_board(workspace_id)
        click.echo(f"Tasks board ID: {tasks_board['id']}")
        click.echo(f"Registry board ID: {registry_board['id']}")
        click.echo("\nAdd these to your .env file:")
        click.echo(f"MONDAY_BOARD_ID={tasks_board['id']}")
        click.echo(f"MONDAY_REGISTRY_BOARD_ID={registry_board['id']}")

    asyncio.run(_setup())


if __name__ == "__main__":
    cli()
