"""Tests for Monday.com board-level tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monday_mcp.tools.boards import get_board_summary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client() -> AsyncMock:
    """Return a mock MondayClient with all async methods pre-configured."""
    return AsyncMock()


@pytest.fixture(autouse=True)
def _patch_get_client(mock_client: AsyncMock) -> Any:
    """Patch get_client() to return the mock client for every test."""
    with patch("monday_mcp.tools.boards.get_client", return_value=mock_client):
        yield


# ---------------------------------------------------------------------------
# get_board_summary()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_board_summary_groups_items_by_status(
    mock_client: AsyncMock,
    monday_board_response: dict[str, Any],
    monday_items_response: dict[str, Any],
) -> None:
    """get_board_summary() groups items by their Status column text."""
    mock_client.get_board.return_value = monday_board_response["data"]["boards"][0]
    mock_client.get_items.return_value = (
        monday_items_response["data"]["boards"][0]["items_page"]
    )

    result = await get_board_summary(board_id=123456789)

    assert result["board_name"] == "Agent Tasks"
    assert result["total_items"] == 3
    by_status = result["by_status"]
    assert "In Progress" in by_status
    assert "To Do" in by_status
    assert "In Review" in by_status
    assert len(by_status["In Progress"]) == 1
    assert len(by_status["To Do"]) == 1
    assert len(by_status["In Review"]) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_board_summary_handles_empty_board(
    mock_client: AsyncMock,
    monday_board_response: dict[str, Any],
) -> None:
    """get_board_summary() handles a board with no items gracefully."""
    mock_client.get_board.return_value = monday_board_response["data"]["boards"][0]
    mock_client.get_items.return_value = {"cursor": None, "items": []}

    result = await get_board_summary(board_id=123456789)

    assert result["board_name"] == "Agent Tasks"
    assert result["total_items"] == 0
    assert result["by_status"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_board_summary_handles_pagination(
    mock_client: AsyncMock,
    monday_board_response: dict[str, Any],
) -> None:
    """get_board_summary() follows cursor pagination to collect all items."""
    mock_client.get_board.return_value = monday_board_response["data"]["boards"][0]

    page1 = {
        "cursor": "next_cursor_abc",
        "items": [
            {
                "id": "111",
                "name": "Task A",
                "group": {"id": "topics", "title": "To Do"},
                "column_values": [
                    {"id": "status", "type": "status", "text": "To Do", "value": '{"index":0}'},
                    {"id": "text", "type": "text", "text": "alice", "value": '"alice"'},
                    {"id": "priority", "type": "status", "text": "High", "value": '{"index":4}'},
                ],
            },
        ],
    }
    page2 = {
        "cursor": None,
        "items": [
            {
                "id": "222",
                "name": "Task B",
                "group": {"id": "group_1", "title": "In Progress"},
                "column_values": [
                    {"id": "status", "type": "status", "text": "In Progress", "value": '{"index":1}'},
                    {"id": "text", "type": "text", "text": "bob", "value": '"bob"'},
                    {"id": "priority", "type": "status", "text": "Low", "value": '{"index":0}'},
                ],
            },
        ],
    }
    mock_client.get_items.side_effect = [page1, page2]

    result = await get_board_summary(board_id=123456789)

    assert result["total_items"] == 2
    assert mock_client.get_items.await_count == 2
    assert "To Do" in result["by_status"]
    assert "In Progress" in result["by_status"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_board_summary_extracts_correct_fields(
    mock_client: AsyncMock,
    monday_board_response: dict[str, Any],
    monday_items_response: dict[str, Any],
) -> None:
    """get_board_summary() extracts id, name, assignee, priority, and group for each item."""
    mock_client.get_board.return_value = monday_board_response["data"]["boards"][0]
    mock_client.get_items.return_value = (
        monday_items_response["data"]["boards"][0]["items_page"]
    )

    result = await get_board_summary(board_id=123456789)

    # Check the "In Progress" item has the correct fields.
    in_progress_items = result["by_status"]["In Progress"]
    assert len(in_progress_items) == 1
    item = in_progress_items[0]
    assert item["id"] == "111"
    assert item["name"] == "Implement auth service"
    assert item["assignee"] == "developer"
    assert item["priority"] == "High"
    assert item["group"] == "In Progress"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_board_summary_uses_unknown_for_missing_status(
    mock_client: AsyncMock,
    monday_board_response: dict[str, Any],
) -> None:
    """get_board_summary() uses 'Unknown' as the status when the status column is empty."""
    mock_client.get_board.return_value = monday_board_response["data"]["boards"][0]
    mock_client.get_items.return_value = {
        "cursor": None,
        "items": [
            {
                "id": "999",
                "name": "No status task",
                "group": {"id": "topics", "title": "To Do"},
                "column_values": [
                    {"id": "status", "type": "status", "text": "", "value": None},
                    {"id": "text", "type": "text", "text": "dev", "value": '"dev"'},
                    {"id": "priority", "type": "status", "text": "Low", "value": '{"index":0}'},
                ],
            },
        ],
    }

    result = await get_board_summary(board_id=123456789)

    assert "Unknown" in result["by_status"]
    assert len(result["by_status"]["Unknown"]) == 1
