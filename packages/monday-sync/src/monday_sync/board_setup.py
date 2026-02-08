"""Set up the Monday.com board schema for agent task management."""

from __future__ import annotations

import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"

# Board column definitions for the Tasks board
TASK_COLUMNS = [
    {"id": "status", "title": "Status", "type": "status"},
    {"id": "priority", "title": "Priority", "type": "status"},
    {"id": "assignee", "title": "Assignee", "type": "text"},
    {"id": "task_type", "title": "Type", "type": "dropdown"},
    {"id": "context_id", "title": "Context ID", "type": "text"},
]

# Status column labels and colors
STATUS_LABELS = {
    "To Do": 0,        # default gray
    "In Progress": 1,  # blue
    "In Review": 4,    # purple
    "Done": 5,         # green
    "Blocked": 2,      # red
}

PRIORITY_LABELS = {
    "Low": 0,
    "Medium": 1,
    "High": 4,
    "Critical": 2,
}

TASK_TYPE_OPTIONS = ["Feature", "Bug", "Chore", "Spike"]

# Board groups
BOARD_GROUPS = ["To Do", "In Progress", "In Review", "Done", "Blocked"]


def _get_headers() -> dict[str, str]:
    token = os.environ.get("MONDAY_API_TOKEN")
    if not token:
        raise ValueError("MONDAY_API_TOKEN environment variable is required")
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }


async def create_tasks_board(workspace_id: int | None = None) -> dict:
    """Create a new Monday.com board with the correct schema for agent tasks.

    Args:
        workspace_id: Optional workspace ID. If None, creates in the default workspace.

    Returns:
        The created board data including board ID.
    """
    workspace_clause = f", workspace_id: {workspace_id}" if workspace_id else ""
    query = f"""
    mutation {{
        create_board(
            board_name: "Agent Tasks",
            board_kind: public
            {workspace_clause}
        ) {{
            id
            name
        }}
    }}
    """

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MONDAY_API_URL,
            json={"query": query},
            headers=_get_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Monday.com API error: {data['errors']}")

    board = data["data"]["create_board"]
    board_id = int(board["id"])
    logger.info("Created board '%s' with ID %d", board["name"], board_id)

    # Set up columns
    await _setup_columns(board_id)

    # Set up groups
    await _setup_groups(board_id)

    return board


async def _setup_columns(board_id: int) -> None:
    """Add custom columns to the board."""
    async with httpx.AsyncClient() as client:
        # Create text columns
        for col in TASK_COLUMNS:
            if col["type"] == "text":
                query = """
                mutation ($boardId: ID!, $title: String!, $columnType: ColumnType!) {
                    create_column(board_id: $boardId, title: $title, column_type: $columnType) {
                        id
                        title
                    }
                }
                """
                variables = {
                    "boardId": str(board_id),
                    "title": col["title"],
                    "columnType": "text",
                }
                resp = await client.post(
                    MONDAY_API_URL,
                    json={"query": query, "variables": variables},
                    headers=_get_headers(),
                    timeout=30.0,
                )
                resp.raise_for_status()
                result = resp.json()
                if "errors" in result:
                    logger.warning(
                        "Column '%s' may already exist: %s",
                        col["title"],
                        result["errors"],
                    )
                else:
                    logger.info("Created column: %s", col["title"])

        # Create dropdown column for Type
        dropdown_labels = json.dumps(
            {"labels": [{"id": i, "name": t} for i, t in enumerate(TASK_TYPE_OPTIONS)]}
        )
        query = """
        mutation ($boardId: ID!, $title: String!, $columnType: ColumnType!, $defaults: JSON!) {
            create_column(board_id: $boardId, title: $title, column_type: $columnType, defaults: $defaults) {
                id
                title
            }
        }
        """
        variables = {
            "boardId": str(board_id),
            "title": "Type",
            "columnType": "dropdown",
            "defaults": dropdown_labels,
        }
        resp = await client.post(
            MONDAY_API_URL,
            json={"query": query, "variables": variables},
            headers=_get_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        logger.info("Created dropdown column: Type")


async def _setup_groups(board_id: int) -> None:
    """Create board groups for task statuses."""
    async with httpx.AsyncClient() as client:
        for group_name in BOARD_GROUPS:
            query = """
            mutation ($boardId: ID!, $groupName: String!) {
                create_group(board_id: $boardId, group_name: $groupName) {
                    id
                }
            }
            """
            variables = {
                "boardId": str(board_id),
                "groupName": group_name,
            }
            resp = await client.post(
                MONDAY_API_URL,
                json={"query": query, "variables": variables},
                headers=_get_headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                logger.warning(
                    "Group '%s' may already exist: %s",
                    group_name,
                    result["errors"],
                )
            else:
                logger.info("Created group: %s", group_name)


async def setup_registry_board(workspace_id: int | None = None) -> dict:
    """Create a Monday.com board to serve as the agent registry.

    This board tracks all registered agents and their metadata.
    """
    workspace_clause = f", workspace_id: {workspace_id}" if workspace_id else ""
    query = f"""
    mutation {{
        create_board(
            board_name: "Agent Registry",
            board_kind: public
            {workspace_clause}
        ) {{
            id
            name
        }}
    }}
    """

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MONDAY_API_URL,
            json={"query": query},
            headers=_get_headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Monday.com API error: {data['errors']}")

    board = data["data"]["create_board"]
    board_id = int(board["id"])
    logger.info("Created registry board '%s' with ID %d", board["name"], board_id)

    # Add columns for agent metadata
    async with httpx.AsyncClient() as client:
        for col_title, col_type in [
            ("Agent Name", "text"),
            ("Display Name", "text"),
            ("Description", "text"),
            ("Port", "numbers"),
            ("Version", "text"),
            ("Status", "status"),
            ("Tags", "text"),
        ]:
            query = """
            mutation ($boardId: ID!, $title: String!, $columnType: ColumnType!) {
                create_column(board_id: $boardId, title: $title, column_type: $columnType) {
                    id
                }
            }
            """
            variables = {
                "boardId": str(board_id),
                "title": col_title,
                "columnType": col_type,
            }
            resp = await client.post(
                MONDAY_API_URL,
                json={"query": query, "variables": variables},
                headers=_get_headers(),
                timeout=30.0,
            )
            resp.raise_for_status()

    return board
