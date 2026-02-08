"""MCP tools for Monday.com updates (comments) on items."""

from __future__ import annotations

import logging
from typing import Any

from monday_mcp.client import get_client

logger = logging.getLogger(__name__)


async def add_task_comment(item_id: int, body: str) -> dict[str, Any]:
    """Add a comment (update) to a Monday.com item.

    Args:
        item_id: The ID of the item to comment on.
        body: The comment text. Supports Monday.com's rich-text HTML subset.

    Returns:
        The created update data including its ID and timestamp.
    """
    if not body or not body.strip():
        raise ValueError("Comment body must not be empty.")

    client = get_client()
    update = await client.create_update(item_id=item_id, body=body)
    logger.info("Added comment to item %s (update id=%s)", item_id, update.get("id"))
    return update
