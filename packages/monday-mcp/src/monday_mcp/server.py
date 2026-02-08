"""FastMCP server exposing Monday.com operations as MCP tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from monday_mcp.tools.boards import get_board_summary as _get_board_summary
from monday_mcp.tools.items import (
    create_task as _create_task,
    get_my_tasks as _get_my_tasks,
    get_task_details as _get_task_details,
    update_task_status as _update_task_status,
)
from monday_mcp.tools.subitems import (
    create_subtask as _create_subtask,
    move_task_to_group as _move_task_to_group,
)
from monday_mcp.tools.updates import add_task_comment as _add_task_comment

logger = logging.getLogger(__name__)

mcp = FastMCP("monday")

# ---------------------------------------------------------------------------
# Tool registrations
# ---------------------------------------------------------------------------


@mcp.tool()
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
) -> str:
    """Create a new task on a Monday.com board.

    Args:
        board_id: The ID of the Monday.com board.
        group_id: The ID of the group to create the item in.
        name: The name / title of the task.
        status: Task status. One of: To Do, In Progress, In Review, Done, Blocked.
        assignee: Name of the person or agent assigned to this task.
        priority: Priority level. One of: Low, Medium, High, Critical.
        task_type: Task type. One of: Feature, Bug, Chore, Spike.
        description: Optional description added as the first comment.
        context_id: Optional A2A context ID for tracing.
    """
    result = await _create_task(
        board_id=board_id,
        group_id=group_id,
        name=name,
        status=status,
        assignee=assignee,
        priority=priority,
        task_type=task_type,
        description=description,
        context_id=context_id,
    )
    return json.dumps(result)


@mcp.tool()
async def update_task_status(
    board_id: int,
    item_id: int,
    status: str,
    comment: str | None = None,
) -> str:
    """Update the status of an existing task and optionally add a comment.

    Args:
        board_id: The ID of the board containing the item.
        item_id: The ID of the item to update.
        status: New status value. One of: To Do, In Progress, In Review, Done, Blocked.
        comment: Optional comment to add alongside the status change.
    """
    result = await _update_task_status(
        board_id=board_id,
        item_id=item_id,
        status=status,
        comment=comment,
    )
    return json.dumps(result)


@mcp.tool()
async def get_my_tasks(
    board_id: int,
    assignee: str,
) -> str:
    """Get all tasks on a board assigned to a specific person or agent.

    Args:
        board_id: The ID of the Monday.com board.
        assignee: The assignee name to filter by (case-insensitive match).
    """
    result = await _get_my_tasks(board_id=board_id, assignee=assignee)
    return json.dumps(result)


@mcp.tool()
async def get_task_details(item_id: int) -> str:
    """Get full details of a task including column values, subitems, and comments.

    Args:
        item_id: The ID of the item to retrieve.
    """
    result = await _get_task_details(item_id=item_id)
    return json.dumps(result)


@mcp.tool()
async def get_board_summary(board_id: int) -> str:
    """Get a summary of all tasks on a board grouped by status.

    Returns task counts and details per status bucket, with assignee and
    priority information for each task.

    Args:
        board_id: The ID of the Monday.com board.
    """
    result = await _get_board_summary(board_id=board_id)
    return json.dumps(result)


@mcp.tool()
async def add_task_comment(item_id: int, body: str) -> str:
    """Add a comment (update) to a Monday.com item.

    Args:
        item_id: The ID of the item to comment on.
        body: The comment text. Supports Monday.com rich-text HTML.
    """
    result = await _add_task_comment(item_id=item_id, body=body)
    return json.dumps(result)


@mcp.tool()
async def create_subtask(
    parent_item_id: int,
    name: str,
    status: str | None = None,
    assignee: str | None = None,
) -> str:
    """Create a subitem (subtask) under a parent Monday.com item.

    Args:
        parent_item_id: The ID of the parent item.
        name: The name / title of the subtask.
        status: Optional status. One of: To Do, In Progress, In Review, Done, Blocked.
        assignee: Optional assignee name for the subtask.
    """
    result = await _create_subtask(
        parent_item_id=parent_item_id,
        name=name,
        status=status,
        assignee=assignee,
    )
    return json.dumps(result)


@mcp.tool()
async def move_task_to_group(item_id: int, group_id: str) -> str:
    """Move a Monday.com item to a different group on the same board.

    Args:
        item_id: The ID of the item to move.
        group_id: The target group ID.
    """
    result = await _move_task_to_group(item_id=item_id, group_id=group_id)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the Monday.com MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
