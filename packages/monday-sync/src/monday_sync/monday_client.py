"""Shared Monday.com GraphQL client."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"
DEFAULT_TIMEOUT = 30.0
API_VERSION = "2024-10"


def get_headers() -> dict[str, str]:
    """Build auth headers from MONDAY_API_TOKEN env var."""
    token = os.environ.get("MONDAY_API_TOKEN")
    if not token:
        raise ValueError("MONDAY_API_TOKEN environment variable is required")
    return {
        "Authorization": token,
        "Content-Type": "application/json",
        "API-Version": API_VERSION,
    }


async def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query against the Monday.com API.

    Raises:
        RuntimeError: If the response contains GraphQL errors.
        httpx.HTTPStatusError: If the HTTP request fails.
    """
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            MONDAY_API_URL,
            json=payload,
            headers=get_headers(),
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"Monday.com API error: {data['errors']}")

    return data


async def get_board_items(board_id: int | str) -> list[dict[str, Any]]:
    """Fetch all items from a board.

    Returns:
        List of item dicts with id, name, and column_values.
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
    data = await graphql(query, {"boardId": [str(board_id)]})
    boards = data.get("data", {}).get("boards", [])
    if not boards:
        return []
    return boards[0].get("items_page", {}).get("items", [])


async def update_column_value(
    board_id: int | str,
    item_id: str,
    column_id: str,
    value: str,
) -> dict[str, Any]:
    """Update a single column value on an item.

    Args:
        board_id: The board ID.
        item_id: The item ID.
        column_id: The column ID to update.
        value: JSON-encoded column value.
    """
    query = """
    mutation ($boardId: ID!, $itemId: ID!, $columnId: String!, $value: JSON!) {
        change_simple_column_value(board_id: $boardId, item_id: $itemId, column_id: $columnId, value: $value) {
            id
        }
    }
    """
    return await graphql(query, {
        "boardId": str(board_id),
        "itemId": item_id,
        "columnId": column_id,
        "value": value,
    })
