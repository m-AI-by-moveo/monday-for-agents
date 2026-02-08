"""MCP tools for Monday.com board-level operations."""

from __future__ import annotations

import logging
from typing import Any

from monday_mcp.client import get_client

logger = logging.getLogger(__name__)


async def get_board_summary(board_id: int) -> dict[str, Any]:
    """Get a summary of all tasks on a board, grouped by status.

    Fetches every item on the board (paginating as needed) and organises
    them into buckets keyed by their *Status* column label.  Each item
    entry includes the task name, assignee, and priority.

    Args:
        board_id: The ID of the Monday.com board.

    Returns:
        A dict with ``board_name``, ``total_items``, and ``by_status``
        (a mapping of status label to a list of lightweight task dicts).
    """
    client = get_client()

    # Fetch board metadata for the name.
    board = await client.get_board(board_id)
    board_name: str = board.get("name", str(board_id))

    # Paginate through all items.
    all_items: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = await client.get_items(board_id=board_id, cursor=cursor)
        all_items.extend(page.get("items", []))
        cursor = page.get("cursor")
        if not cursor:
            break

    # Build the status-grouped summary.
    by_status: dict[str, list[dict[str, str | None]]] = {}
    for item in all_items:
        cols = {c["id"]: c.get("text") for c in item.get("column_values", [])}
        status = cols.get("status") or "Unknown"
        assignee = cols.get("text")
        priority = cols.get("priority")

        entry = {
            "id": item["id"],
            "name": item["name"],
            "assignee": assignee,
            "priority": priority,
            "group": item.get("group", {}).get("title"),
        }
        by_status.setdefault(status, []).append(entry)

    summary = {
        "board_id": board_id,
        "board_name": board_name,
        "total_items": len(all_items),
        "by_status": by_status,
    }

    logger.info(
        "Board '%s' summary: %d items across %d statuses",
        board_name,
        len(all_items),
        len(by_status),
    )
    return summary
