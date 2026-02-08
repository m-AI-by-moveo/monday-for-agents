"""Tests for the FastMCP server registration and tool wiring."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monday_mcp.server import mcp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_tool_names() -> set[str]:
    """Return the set of registered tool names from the FastMCP instance."""
    # FastMCP stores tools in a dict keyed by tool name.
    return set(mcp._tool_manager._tools.keys())


def _get_tool(name: str) -> Any:
    """Return the tool object registered under the given name."""
    return mcp._tool_manager._tools[name]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_all_eight_tools_are_registered() -> None:
    """The MCP server registers exactly 8 tools."""
    tool_names = _get_tool_names()
    expected = {
        "create_task",
        "update_task_status",
        "get_my_tasks",
        "get_task_details",
        "get_board_summary",
        "add_task_comment",
        "create_subtask",
        "move_task_to_group",
    }
    assert tool_names == expected


@pytest.mark.unit
def test_each_tool_has_a_docstring() -> None:
    """Every registered tool has a non-empty description."""
    for name in _get_tool_names():
        tool = _get_tool(name)
        description = tool.description
        assert description, f"Tool '{name}' has no description"
        assert len(description) > 10, f"Tool '{name}' has a very short description"


# ---------------------------------------------------------------------------
# Tool delegation
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_task_delegates_to_items_module(
    monday_create_item_response: dict[str, Any],
) -> None:
    """The create_task server tool delegates to tools.items.create_task."""
    expected = monday_create_item_response["data"]["create_item"]
    with patch(
        "monday_mcp.server._create_task",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_fn:
        from monday_mcp.server import create_task

        result = await create_task(
            board_id=123456789,
            group_id="topics",
            name="Test",
        )
        mock_fn.assert_awaited_once()
        assert json.loads(result)["id"] == "666"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_task_status_delegates_to_items_module(
    monday_change_columns_response: dict[str, Any],
) -> None:
    """The update_task_status server tool delegates to tools.items.update_task_status."""
    expected = monday_change_columns_response["data"]["change_multiple_column_values"]
    with patch(
        "monday_mcp.server._update_task_status",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_fn:
        from monday_mcp.server import update_task_status

        result = await update_task_status(
            board_id=123456789,
            item_id=111,
            status="Done",
        )
        mock_fn.assert_awaited_once()
        assert json.loads(result)["id"] == "111"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_my_tasks_delegates_to_items_module(
    monday_items_response: dict[str, Any],
) -> None:
    """The get_my_tasks server tool delegates to tools.items.get_my_tasks."""
    items = monday_items_response["data"]["boards"][0]["items_page"]["items"]
    with patch(
        "monday_mcp.server._get_my_tasks",
        new_callable=AsyncMock,
        return_value=items,
    ) as mock_fn:
        from monday_mcp.server import get_my_tasks

        result = await get_my_tasks(board_id=123456789, assignee="developer")
        mock_fn.assert_awaited_once()
        parsed = json.loads(result)
        assert len(parsed) == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_task_details_delegates_to_items_module(
    monday_item_detail_response: dict[str, Any],
) -> None:
    """The get_task_details server tool delegates to tools.items.get_task_details."""
    expected = monday_item_detail_response["data"]["items"][0]
    with patch(
        "monday_mcp.server._get_task_details",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_fn:
        from monday_mcp.server import get_task_details

        result = await get_task_details(item_id=111)
        mock_fn.assert_awaited_once()
        assert json.loads(result)["name"] == "Implement auth service"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_board_summary_delegates_to_boards_module() -> None:
    """The get_board_summary server tool delegates to tools.boards.get_board_summary."""
    mock_summary = {"board_name": "Test", "total_items": 0, "by_status": {}}
    with patch(
        "monday_mcp.server._get_board_summary",
        new_callable=AsyncMock,
        return_value=mock_summary,
    ) as mock_fn:
        from monday_mcp.server import get_board_summary

        result = await get_board_summary(board_id=123456789)
        mock_fn.assert_awaited_once()
        assert json.loads(result)["board_name"] == "Test"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_task_comment_delegates_to_updates_module(
    monday_create_update_response: dict[str, Any],
) -> None:
    """The add_task_comment server tool delegates to tools.updates.add_task_comment."""
    expected = monday_create_update_response["data"]["create_update"]
    with patch(
        "monday_mcp.server._add_task_comment",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_fn:
        from monday_mcp.server import add_task_comment

        result = await add_task_comment(item_id=111, body="Hello")
        mock_fn.assert_awaited_once()
        assert json.loads(result)["id"] == "upd_new"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subtask_delegates_to_subitems_module(
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """The create_subtask server tool delegates to tools.subitems.create_subtask."""
    expected = monday_create_subitem_response["data"]["create_subitem"]
    with patch(
        "monday_mcp.server._create_subtask",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_fn:
        from monday_mcp.server import create_subtask

        result = await create_subtask(
            parent_item_id=111,
            name="Subtask",
        )
        mock_fn.assert_awaited_once()
        assert json.loads(result)["id"] == "777"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_task_to_group_delegates_to_subitems_module(
    monday_move_item_response: dict[str, Any],
) -> None:
    """The move_task_to_group server tool delegates to tools.subitems.move_task_to_group."""
    expected = monday_move_item_response["data"]["move_item_to_group"]
    with patch(
        "monday_mcp.server._move_task_to_group",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_fn:
        from monday_mcp.server import move_task_to_group

        result = await move_task_to_group(item_id=111, group_id="group_3")
        mock_fn.assert_awaited_once()
        assert json.loads(result)["group"]["title"] == "Done"
