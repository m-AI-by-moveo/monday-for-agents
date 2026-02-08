"""MCP tools for Monday.com item (task) CRUD operations."""

from __future__ import annotations

import logging
from typing import Any

from monday_mcp.client import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column-value helpers
# ---------------------------------------------------------------------------

_STATUS_VALUES = {"To Do", "In Progress", "In Review", "Done", "Blocked"}
_PRIORITY_VALUES = {"Low", "Medium", "High", "Critical"}
_TYPE_VALUES = {"Feature", "Bug", "Chore", "Spike"}


def _build_column_values(
    *,
    status: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    task_type: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    """Build the column_values dict understood by the Monday.com API."""
    cols: dict[str, Any] = {}
    if status:
        if status not in _STATUS_VALUES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(_STATUS_VALUES))}"
            )
        cols["status"] = {"label": status}
    if priority:
        if priority not in _PRIORITY_VALUES:
            raise ValueError(
                f"Invalid priority '{priority}'. Must be one of: {', '.join(sorted(_PRIORITY_VALUES))}"
            )
        cols["priority"] = {"label": priority}
    if assignee:
        cols["text"] = assignee
    if task_type:
        if task_type not in _TYPE_VALUES:
            raise ValueError(
                f"Invalid type '{task_type}'. Must be one of: {', '.join(sorted(_TYPE_VALUES))}"
            )
        cols["dropdown"] = {"labels": [task_type]}
    if context_id:
        cols["text0"] = context_id
    return cols


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def _resolve_group_id(client: Any, board_id: int, group_id: str) -> str:
    """Resolve a group ID or group title to the actual Monday.com group ID.

    If *group_id* matches an existing group ID exactly, it is returned as-is.
    Otherwise, the board's groups are fetched and a case-insensitive title
    match is attempted.  Falls back to the first group on the board if no
    match is found.
    """
    board = await client.get_board(board_id)
    groups = board.get("groups", [])

    # Direct ID match
    for g in groups:
        if g["id"] == group_id:
            return group_id

    # Title match (case-insensitive)
    for g in groups:
        if g["title"].lower() == group_id.lower():
            logger.info(
                "Resolved group title '%s' to ID '%s' on board %s",
                group_id, g["id"], board_id,
            )
            return g["id"]

    # Fallback: use the first group
    if groups:
        logger.warning(
            "Group '%s' not found on board %s. Using first group '%s' (id=%s). "
            "Available groups: %s",
            group_id, board_id, groups[0]["title"], groups[0]["id"],
            [(g["id"], g["title"]) for g in groups],
        )
        return groups[0]["id"]

    raise ValueError(f"Board {board_id} has no groups")


async def create_task(
    board_id: int,
    group_id: str,
    name: str,
    status: str | None = None,
    assignee: str | None = None,
    priority: str | None = None,
    task_type: str | None = None,
    description: str | None = None,
    context_id: str | None = None,
) -> dict[str, Any]:
    """Create a new task (item) on a Monday.com board.

    Args:
        board_id: The ID of the Monday.com board.
        group_id: The ID or display name of the group to create the item in.
            If a display name is provided (e.g. "To Do"), it will be resolved
            to the actual group ID automatically.
        name: The name / title of the task.
        status: Task status. One of: To Do, In Progress, In Review, Done, Blocked.
        assignee: Name of the person or agent assigned to this task.
        priority: Priority level. One of: Low, Medium, High, Critical.
        task_type: Task type. One of: Feature, Bug, Chore, Spike.
        description: Optional description added as the first update/comment.
        context_id: Optional A2A context ID for tracing.

    Returns:
        The created item data from Monday.com.
    """
    client = get_client()

    # Resolve group name to ID if needed
    resolved_group_id = await _resolve_group_id(client, board_id, group_id)

    column_values = _build_column_values(
        status=status,
        assignee=assignee,
        priority=priority,
        task_type=task_type,
        context_id=context_id,
    )

    item = await client.create_item(
        board_id=board_id,
        group_id=resolved_group_id,
        item_name=name,
        column_values=column_values or None,
    )

    # If a description was provided, attach it as the first update.
    if description:
        await client.create_update(item_id=int(item["id"]), body=description)

    logger.info("Created task '%s' (id=%s) on board %s", name, item["id"], board_id)
    return item


async def update_task_status(
    board_id: int,
    item_id: int,
    status: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Update the status of an existing task and optionally add a comment.

    Args:
        board_id: The ID of the board containing the item.
        item_id: The ID of the item to update.
        status: New status value. One of: To Do, In Progress, In Review, Done, Blocked.
        comment: Optional comment to add alongside the status change.

    Returns:
        The updated item data from Monday.com.
    """
    if status not in _STATUS_VALUES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(sorted(_STATUS_VALUES))}"
        )

    client = get_client()
    item = await client.change_column_values(
        item_id=item_id,
        board_id=board_id,
        column_values={"status": {"label": status}},
    )

    if comment:
        await client.create_update(item_id=item_id, body=comment)

    logger.info("Updated task %s status to '%s'", item_id, status)
    return item


async def get_my_tasks(
    board_id: int,
    assignee: str,
) -> list[dict[str, Any]]:
    """Get all tasks on a board assigned to a specific person or agent.

    Iterates through all items using cursor-based pagination and filters
    by the text column matching the given *assignee*.

    Args:
        board_id: The ID of the Monday.com board.
        assignee: The assignee name to filter by (case-insensitive match).

    Returns:
        A list of matching item dicts.
    """
    client = get_client()
    matched: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        page = await client.get_items(board_id=board_id, cursor=cursor)
        for item in page.get("items", []):
            for col in item.get("column_values", []):
                if col["id"] == "text" and col.get("text", "").lower() == assignee.lower():
                    matched.append(item)
                    break
        cursor = page.get("cursor")
        if not cursor:
            break

    logger.info("Found %d tasks assigned to '%s' on board %s", len(matched), assignee, board_id)
    return matched


async def get_task_details(item_id: int) -> dict[str, Any]:
    """Get full details of a task including column values, subitems, and comments.

    Args:
        item_id: The ID of the item to retrieve.

    Returns:
        Complete item data with subitems and recent updates.
    """
    client = get_client()
    item = await client.get_item(item_id)
    logger.info("Retrieved details for task %s ('%s')", item_id, item.get("name"))
    return item
