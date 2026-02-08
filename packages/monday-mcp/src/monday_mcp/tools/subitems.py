"""MCP tools for Monday.com subitems and item movement."""

from __future__ import annotations

import logging
from typing import Any

from monday_mcp.client import get_client

logger = logging.getLogger(__name__)

_STATUS_VALUES = {"To Do", "In Progress", "In Review", "Done", "Blocked"}


async def create_subtask(
    parent_item_id: int,
    name: str,
    status: str | None = None,
    assignee: str | None = None,
) -> dict[str, Any]:
    """Create a subitem (subtask) under a parent Monday.com item.

    Args:
        parent_item_id: The ID of the parent item.
        name: The name / title of the subtask.
        status: Optional status. One of: To Do, In Progress, In Review, Done, Blocked.
        assignee: Optional assignee name for the subtask.

    Returns:
        The created subitem data from Monday.com.
    """
    column_values: dict[str, Any] = {}
    if status:
        if status not in _STATUS_VALUES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(_STATUS_VALUES))}"
            )
        column_values["status"] = {"label": status}
    if assignee:
        column_values["text"] = assignee

    client = get_client()
    subitem = await client.create_subitem(
        parent_item_id=parent_item_id,
        item_name=name,
        column_values=column_values or None,
    )

    logger.info(
        "Created subtask '%s' (id=%s) under parent %s",
        name,
        subitem.get("id"),
        parent_item_id,
    )
    return subitem


async def move_task_to_group(item_id: int, group_id: str) -> dict[str, Any]:
    """Move a Monday.com item to a different group on the same board.

    Args:
        item_id: The ID of the item to move.
        group_id: The target group ID.

    Returns:
        The moved item data including its new group.
    """
    client = get_client()
    item = await client.move_item_to_group(item_id=item_id, group_id=group_id)
    logger.info("Moved item %s to group '%s'", item_id, group_id)
    return item
