"""Tests for Monday.com item (task) tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monday_mcp.tools.items import (
    _build_column_values,
    create_task,
    get_my_tasks,
    get_task_details,
    update_task_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_client() -> AsyncMock:
    """Return a mock MondayClient with all async methods pre-configured."""
    client = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def _patch_get_client(mock_client: AsyncMock) -> Any:
    """Patch get_client() to return the mock client for every test."""
    with patch("monday_mcp.tools.items.get_client", return_value=mock_client):
        yield


# ---------------------------------------------------------------------------
# _build_column_values()
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_column_values_with_all_params() -> None:
    """_build_column_values() populates all column keys when given every parameter."""
    result = _build_column_values(
        status="In Progress",
        assignee="developer",
        priority="High",
        task_type="Feature",
        context_id="ctx-123",
    )
    assert result == {
        "status": {"label": "In Progress"},
        "priority": {"label": "High"},
        "text": "developer",
        "dropdown": {"labels": ["Feature"]},
        "text0": "ctx-123",
    }


@pytest.mark.unit
def test_build_column_values_with_no_params() -> None:
    """_build_column_values() returns an empty dict when no arguments are given."""
    result = _build_column_values()
    assert result == {}


@pytest.mark.unit
def test_build_column_values_with_only_assignee() -> None:
    """_build_column_values() sets only the text column for assignee."""
    result = _build_column_values(assignee="alice")
    assert result == {"text": "alice"}


@pytest.mark.unit
def test_build_column_values_with_status_and_priority() -> None:
    """_build_column_values() sets status and priority labels."""
    result = _build_column_values(status="Done", priority="Critical")
    assert result == {
        "status": {"label": "Done"},
        "priority": {"label": "Critical"},
    }


@pytest.mark.unit
def test_build_column_values_raises_for_invalid_status() -> None:
    """_build_column_values() raises ValueError for an unrecognised status."""
    with pytest.raises(ValueError, match="Invalid status 'Not Real'"):
        _build_column_values(status="Not Real")


@pytest.mark.unit
def test_build_column_values_raises_for_invalid_priority() -> None:
    """_build_column_values() raises ValueError for an unrecognised priority."""
    with pytest.raises(ValueError, match="Invalid priority 'Urgent'"):
        _build_column_values(priority="Urgent")


@pytest.mark.unit
def test_build_column_values_raises_for_invalid_type() -> None:
    """_build_column_values() raises ValueError for an unrecognised task type."""
    with pytest.raises(ValueError, match="Invalid type 'Epic'"):
        _build_column_values(task_type="Epic")


# ---------------------------------------------------------------------------
# create_task()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_task_calls_client_with_all_params(
    mock_client: AsyncMock,
    monday_create_item_response: dict[str, Any],
) -> None:
    """create_task() calls client.create_item with the correct column_values."""
    mock_client.create_item.return_value = monday_create_item_response["data"]["create_item"]

    result = await create_task(
        board_id=123456789,
        group_id="topics",
        name="New task",
        status="To Do",
        assignee="developer",
        priority="High",
        task_type="Feature",
        context_id="ctx-abc",
    )

    mock_client.create_item.assert_awaited_once()
    call_kwargs = mock_client.create_item.call_args.kwargs
    assert call_kwargs["board_id"] == 123456789
    assert call_kwargs["group_id"] == "topics"
    assert call_kwargs["item_name"] == "New task"
    assert call_kwargs["column_values"]["status"] == {"label": "To Do"}
    assert call_kwargs["column_values"]["text"] == "developer"
    assert call_kwargs["column_values"]["priority"] == {"label": "High"}
    assert call_kwargs["column_values"]["dropdown"] == {"labels": ["Feature"]}
    assert call_kwargs["column_values"]["text0"] == "ctx-abc"
    assert result["id"] == "666"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_task_with_description_adds_update(
    mock_client: AsyncMock,
    monday_create_item_response: dict[str, Any],
    monday_create_update_response: dict[str, Any],
) -> None:
    """create_task() adds an update (comment) when description is provided."""
    mock_client.create_item.return_value = monday_create_item_response["data"]["create_item"]
    mock_client.create_update.return_value = monday_create_update_response["data"]["create_update"]

    await create_task(
        board_id=123456789,
        group_id="topics",
        name="New task",
        description="This is the description.",
    )

    mock_client.create_update.assert_awaited_once_with(
        item_id=666,
        body="This is the description.",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_task_without_optional_params(
    mock_client: AsyncMock,
    monday_create_item_response: dict[str, Any],
) -> None:
    """create_task() sends column_values=None when no optional params are given."""
    mock_client.create_item.return_value = monday_create_item_response["data"]["create_item"]

    await create_task(
        board_id=123456789,
        group_id="topics",
        name="Bare task",
    )

    call_kwargs = mock_client.create_item.call_args.kwargs
    assert call_kwargs["column_values"] is None
    mock_client.create_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_task_status()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_task_status_changes_status_column(
    mock_client: AsyncMock,
    monday_change_columns_response: dict[str, Any],
) -> None:
    """update_task_status() calls change_column_values with the status label."""
    mock_client.change_column_values.return_value = (
        monday_change_columns_response["data"]["change_multiple_column_values"]
    )

    result = await update_task_status(
        board_id=123456789,
        item_id=111,
        status="Done",
    )

    mock_client.change_column_values.assert_awaited_once_with(
        item_id=111,
        board_id=123456789,
        column_values={"status": {"label": "Done"}},
    )
    assert result["id"] == "111"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_task_status_adds_comment_when_provided(
    mock_client: AsyncMock,
    monday_change_columns_response: dict[str, Any],
    monday_create_update_response: dict[str, Any],
) -> None:
    """update_task_status() adds a comment when the comment parameter is given."""
    mock_client.change_column_values.return_value = (
        monday_change_columns_response["data"]["change_multiple_column_values"]
    )
    mock_client.create_update.return_value = (
        monday_create_update_response["data"]["create_update"]
    )

    await update_task_status(
        board_id=123456789,
        item_id=111,
        status="Done",
        comment="All done!",
    )

    mock_client.create_update.assert_awaited_once_with(
        item_id=111,
        body="All done!",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_task_status_without_comment_does_not_create_update(
    mock_client: AsyncMock,
    monday_change_columns_response: dict[str, Any],
) -> None:
    """update_task_status() does not call create_update when no comment is given."""
    mock_client.change_column_values.return_value = (
        monday_change_columns_response["data"]["change_multiple_column_values"]
    )

    await update_task_status(
        board_id=123456789,
        item_id=111,
        status="In Progress",
    )

    mock_client.create_update.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_task_status_raises_for_invalid_status(
    mock_client: AsyncMock,
) -> None:
    """update_task_status() raises ValueError for an invalid status value."""
    with pytest.raises(ValueError, match="Invalid status 'Invalid'"):
        await update_task_status(
            board_id=123456789,
            item_id=111,
            status="Invalid",
        )
    mock_client.change_column_values.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_my_tasks()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_my_tasks_filters_by_assignee(
    mock_client: AsyncMock,
    monday_items_response: dict[str, Any],
) -> None:
    """get_my_tasks() returns only items where the text column matches the assignee."""
    mock_client.get_items.return_value = (
        monday_items_response["data"]["boards"][0]["items_page"]
    )

    result = await get_my_tasks(board_id=123456789, assignee="developer")

    assert len(result) == 2
    names = {item["name"] for item in result}
    assert names == {"Implement auth service", "Write API tests"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_my_tasks_case_insensitive(
    mock_client: AsyncMock,
    monday_items_response: dict[str, Any],
) -> None:
    """get_my_tasks() matches the assignee name case-insensitively."""
    mock_client.get_items.return_value = (
        monday_items_response["data"]["boards"][0]["items_page"]
    )

    result = await get_my_tasks(board_id=123456789, assignee="Developer")
    assert len(result) == 2

    result_upper = await get_my_tasks(board_id=123456789, assignee="DEVELOPER")
    assert len(result_upper) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_my_tasks_handles_pagination(
    mock_client: AsyncMock,
) -> None:
    """get_my_tasks() follows cursor pagination across multiple pages."""
    page1 = {
        "cursor": "next_page_cursor",
        "items": [
            {
                "id": "111",
                "name": "Task 1",
                "group": {"id": "topics", "title": "To Do"},
                "column_values": [
                    {"id": "text", "type": "text", "text": "agent", "value": '"agent"'},
                ],
            },
        ],
    }
    page2 = {
        "cursor": None,
        "items": [
            {
                "id": "222",
                "name": "Task 2",
                "group": {"id": "topics", "title": "To Do"},
                "column_values": [
                    {"id": "text", "type": "text", "text": "agent", "value": '"agent"'},
                ],
            },
        ],
    }
    mock_client.get_items.side_effect = [page1, page2]

    result = await get_my_tasks(board_id=123456789, assignee="agent")

    assert len(result) == 2
    assert mock_client.get_items.await_count == 2
    # Verify the second call used the cursor from the first page.
    second_call_kwargs = mock_client.get_items.call_args_list[1].kwargs
    assert second_call_kwargs["cursor"] == "next_page_cursor"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_my_tasks_returns_empty_when_no_match(
    mock_client: AsyncMock,
    monday_items_response: dict[str, Any],
) -> None:
    """get_my_tasks() returns an empty list when no items match the assignee."""
    mock_client.get_items.return_value = (
        monday_items_response["data"]["boards"][0]["items_page"]
    )

    result = await get_my_tasks(board_id=123456789, assignee="nonexistent_user")
    assert result == []


# ---------------------------------------------------------------------------
# get_task_details()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_task_details_returns_full_item(
    mock_client: AsyncMock,
    monday_item_detail_response: dict[str, Any],
) -> None:
    """get_task_details() returns the complete item from client.get_item()."""
    expected_item = monday_item_detail_response["data"]["items"][0]
    mock_client.get_item.return_value = expected_item

    result = await get_task_details(item_id=111)

    mock_client.get_item.assert_awaited_once_with(111)
    assert result["id"] == "111"
    assert result["name"] == "Implement auth service"
    assert len(result["subitems"]) == 2
    assert len(result["updates"]) == 2
