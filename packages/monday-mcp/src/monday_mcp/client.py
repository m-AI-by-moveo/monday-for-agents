"""Async GraphQL client for Monday.com API."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MONDAY_API_URL = "https://api.monday.com/v2"
DEFAULT_PAGE_LIMIT = 500

# Monday.com rate-limit: 10 000 000 complexity points per minute.
_RATE_LIMIT_POINTS_PER_MIN = 10_000_000


class MondayAPIError(Exception):
    """Raised when the Monday.com API returns an error."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class MondayClient:
    """Async wrapper around the Monday.com GraphQL API.

    Initialised from the ``MONDAY_API_TOKEN`` environment variable.
    Provides convenience methods for common board / item operations together
    with cursor-based pagination and basic rate-limit awareness.
    """

    def __init__(self, api_token: str | None = None) -> None:
        self._token = api_token or os.environ.get("MONDAY_API_TOKEN", "")
        if not self._token:
            raise ValueError(
                "Monday.com API token is required. "
                "Set the MONDAY_API_TOKEN environment variable."
            )
        self._client = httpx.AsyncClient(
            base_url=MONDAY_API_URL,
            headers={
                "Authorization": self._token,
                "Content-Type": "application/json",
                "API-Version": "2024-10",
            },
            timeout=30.0,
        )
        # Lightweight rate-limit tracking (complexity points consumed).
        self._complexity_consumed: int = 0
        self._window_start: float = time.monotonic()

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a raw GraphQL query against the Monday.com API.

        Returns the ``data`` portion of the response.  Raises
        :class:`MondayAPIError` if the response contains errors.
        """
        self._check_rate_limit()

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self._client.post("", json=payload)
        response.raise_for_status()
        body = response.json()

        # Track complexity if returned.
        complexity = body.get("complexity") or body.get("data", {}).get("complexity")
        if complexity and isinstance(complexity, dict):
            self._record_complexity(complexity.get("after", 0))

        if "errors" in body:
            msgs = "; ".join(e.get("message", str(e)) for e in body["errors"])
            raise MondayAPIError(f"Monday.com API errors: {msgs}", body["errors"])

        if body.get("error_message"):
            raise MondayAPIError(body["error_message"])

        return body.get("data", body)

    # ------------------------------------------------------------------
    # Board operations
    # ------------------------------------------------------------------

    async def get_board(self, board_id: int) -> dict[str, Any]:
        """Fetch a board including its groups and column definitions."""
        query = """
        query GetBoard($boardId: [ID!]!) {
            boards(ids: $boardId) {
                id
                name
                description
                groups {
                    id
                    title
                    color
                }
                columns {
                    id
                    title
                    type
                    settings_str
                }
            }
        }
        """
        data = await self.execute(query, {"boardId": [str(board_id)]})
        boards = data.get("boards", [])
        if not boards:
            raise MondayAPIError(f"Board {board_id} not found")
        return boards[0]

    # ------------------------------------------------------------------
    # Item operations
    # ------------------------------------------------------------------

    async def get_items(
        self,
        board_id: int,
        limit: int = DEFAULT_PAGE_LIMIT,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of items from *board_id*.

        Uses cursor-based pagination.  The returned dict has keys
        ``cursor`` (str | None) and ``items`` (list).
        """
        query = """
        query GetItems($boardId: [ID!]!, $limit: Int!, $cursor: String) {
            boards(ids: $boardId) {
                items_page(limit: $limit, cursor: $cursor) {
                    cursor
                    items {
                        id
                        name
                        group {
                            id
                            title
                        }
                        column_values {
                            id
                            type
                            text
                            value
                        }
                    }
                }
            }
        }
        """
        variables: dict[str, Any] = {
            "boardId": [str(board_id)],
            "limit": limit,
        }
        if cursor:
            variables["cursor"] = cursor

        data = await self.execute(query, variables)
        boards = data.get("boards", [])
        if not boards:
            raise MondayAPIError(f"Board {board_id} not found")
        return boards[0]["items_page"]

    async def get_item(self, item_id: int) -> dict[str, Any]:
        """Fetch a single item with column values, subitems, and updates."""
        query = """
        query GetItem($itemId: [ID!]!) {
            items(ids: $itemId) {
                id
                name
                group {
                    id
                    title
                }
                board {
                    id
                    name
                }
                column_values {
                    id
                    type
                    text
                    value
                }
                subitems {
                    id
                    name
                    column_values {
                        id
                        type
                        text
                        value
                    }
                }
                updates(limit: 25) {
                    id
                    body
                    text_body
                    created_at
                    creator {
                        name
                    }
                }
            }
        }
        """
        data = await self.execute(query, {"itemId": [str(item_id)]})
        items = data.get("items", [])
        if not items:
            raise MondayAPIError(f"Item {item_id} not found")
        return items[0]

    async def create_item(
        self,
        board_id: int,
        group_id: str,
        item_name: str,
        column_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new item on a board in the given group."""
        query = """
        mutation CreateItem(
            $boardId: ID!,
            $groupId: String!,
            $itemName: String!,
            $columnValues: JSON
        ) {
            create_item(
                board_id: $boardId,
                group_id: $groupId,
                item_name: $itemName,
                column_values: $columnValues
            ) {
                id
                name
                group {
                    id
                    title
                }
                column_values {
                    id
                    type
                    text
                    value
                }
            }
        }
        """
        variables: dict[str, Any] = {
            "boardId": str(board_id),
            "groupId": group_id,
            "itemName": item_name,
        }
        if column_values:
            variables["columnValues"] = json.dumps(column_values)

        data = await self.execute(query, variables)
        return data["create_item"]

    async def change_column_values(
        self,
        item_id: int,
        board_id: int,
        column_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Update column values on an existing item."""
        query = """
        mutation ChangeColumnValues(
            $itemId: ID!,
            $boardId: ID!,
            $columnValues: JSON!
        ) {
            change_multiple_column_values(
                item_id: $itemId,
                board_id: $boardId,
                column_values: $columnValues
            ) {
                id
                name
                column_values {
                    id
                    type
                    text
                    value
                }
            }
        }
        """
        data = await self.execute(
            query,
            {
                "itemId": str(item_id),
                "boardId": str(board_id),
                "columnValues": json.dumps(column_values),
            },
        )
        return data["change_multiple_column_values"]

    async def create_update(self, item_id: int, body: str) -> dict[str, Any]:
        """Add an update (comment) to an item."""
        query = """
        mutation CreateUpdate($itemId: ID!, $body: String!) {
            create_update(item_id: $itemId, body: $body) {
                id
                body
                created_at
            }
        }
        """
        data = await self.execute(
            query,
            {"itemId": str(item_id), "body": body},
        )
        return data["create_update"]

    async def create_subitem(
        self,
        parent_item_id: int,
        item_name: str,
        column_values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a subitem under a parent item."""
        query = """
        mutation CreateSubitem(
            $parentItemId: ID!,
            $itemName: String!,
            $columnValues: JSON
        ) {
            create_subitem(
                parent_item_id: $parentItemId,
                item_name: $itemName,
                column_values: $columnValues
            ) {
                id
                name
                column_values {
                    id
                    type
                    text
                    value
                }
            }
        }
        """
        variables: dict[str, Any] = {
            "parentItemId": str(parent_item_id),
            "itemName": item_name,
        }
        if column_values:
            variables["columnValues"] = json.dumps(column_values)

        data = await self.execute(query, variables)
        return data["create_subitem"]

    async def move_item_to_group(
        self,
        item_id: int,
        group_id: str,
    ) -> dict[str, Any]:
        """Move an item to a different group on the same board."""
        query = """
        mutation MoveItem($itemId: ID!, $groupId: String!) {
            move_item_to_group(item_id: $itemId, group_id: $groupId) {
                id
                name
                group {
                    id
                    title
                }
            }
        }
        """
        data = await self.execute(
            query,
            {"itemId": str(item_id), "groupId": group_id},
        )
        return data["move_item_to_group"]

    # ------------------------------------------------------------------
    # Rate-limit helpers
    # ------------------------------------------------------------------

    def _check_rate_limit(self) -> None:
        """Reset the tracking window and warn if we are close to the limit."""
        now = time.monotonic()
        elapsed = now - self._window_start
        if elapsed >= 60:
            # New window
            self._complexity_consumed = 0
            self._window_start = now
            return

        if self._complexity_consumed >= _RATE_LIMIT_POINTS_PER_MIN * 0.9:
            logger.warning(
                "Approaching Monday.com rate limit: %d / %d complexity points consumed "
                "in current window (%.1fs elapsed).",
                self._complexity_consumed,
                _RATE_LIMIT_POINTS_PER_MIN,
                elapsed,
            )

    def _record_complexity(self, points: int) -> None:
        self._complexity_consumed += points

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_client: MondayClient | None = None


def get_client() -> MondayClient:
    """Return the module-level :class:`MondayClient` singleton.

    The client is lazily initialised on first access so that import-time
    side-effects are avoided.
    """
    global _client
    if _client is None:
        _client = MondayClient()
    return _client
