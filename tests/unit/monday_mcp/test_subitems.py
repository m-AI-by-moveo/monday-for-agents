"""Tests for Monday.com subitems and item movement tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monday_mcp.tools.subitems import create_subtask, move_task_to_group


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
    with patch("monday_mcp.tools.subitems.get_client", return_value=mock_client):
        yield


# ---------------------------------------------------------------------------
# create_subtask()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subtask_with_status_and_assignee(
    mock_client: AsyncMock,
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """create_subtask() sends column_values with status and assignee."""
    mock_client.create_subitem.return_value = (
        monday_create_subitem_response["data"]["create_subitem"]
    )

    result = await create_subtask(
        parent_item_id=111,
        name="New subtask",
        status="In Progress",
        assignee="developer",
    )

    mock_client.create_subitem.assert_awaited_once()
    call_kwargs = mock_client.create_subitem.call_args.kwargs
    assert call_kwargs["parent_item_id"] == 111
    assert call_kwargs["item_name"] == "New subtask"
    expected_cols = {
        "status": {"label": "In Progress"},
        "text": "developer",
    }
    assert call_kwargs["column_values"] == expected_cols
    assert result["id"] == "777"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subtask_without_optional_params(
    mock_client: AsyncMock,
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """create_subtask() sends column_values=None when no optional params are given."""
    mock_client.create_subitem.return_value = (
        monday_create_subitem_response["data"]["create_subitem"]
    )

    await create_subtask(parent_item_id=111, name="Bare subtask")

    call_kwargs = mock_client.create_subitem.call_args.kwargs
    assert call_kwargs["column_values"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subtask_raises_for_invalid_status(
    mock_client: AsyncMock,
) -> None:
    """create_subtask() raises ValueError for an invalid status value."""
    with pytest.raises(ValueError, match="Invalid status 'Cancelled'"):
        await create_subtask(
            parent_item_id=111,
            name="Bad subtask",
            status="Cancelled",
        )

    mock_client.create_subitem.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subtask_with_status_only(
    mock_client: AsyncMock,
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """create_subtask() sends column_values with only status when no assignee given."""
    mock_client.create_subitem.return_value = (
        monday_create_subitem_response["data"]["create_subitem"]
    )

    await create_subtask(
        parent_item_id=111,
        name="Status-only subtask",
        status="To Do",
    )

    call_kwargs = mock_client.create_subitem.call_args.kwargs
    assert call_kwargs["column_values"] == {"status": {"label": "To Do"}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_subtask_with_assignee_only(
    mock_client: AsyncMock,
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """create_subtask() sends column_values with only assignee when no status given."""
    mock_client.create_subitem.return_value = (
        monday_create_subitem_response["data"]["create_subitem"]
    )

    await create_subtask(
        parent_item_id=111,
        name="Assignee-only subtask",
        assignee="alice",
    )

    call_kwargs = mock_client.create_subitem.call_args.kwargs
    assert call_kwargs["column_values"] == {"text": "alice"}


# ---------------------------------------------------------------------------
# move_task_to_group()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_task_to_group_calls_client_correctly(
    mock_client: AsyncMock,
    monday_move_item_response: dict[str, Any],
) -> None:
    """move_task_to_group() delegates to client.move_item_to_group."""
    mock_client.move_item_to_group.return_value = (
        monday_move_item_response["data"]["move_item_to_group"]
    )

    result = await move_task_to_group(item_id=111, group_id="group_3")

    mock_client.move_item_to_group.assert_awaited_once_with(
        item_id=111,
        group_id="group_3",
    )
    assert result["id"] == "111"
    assert result["group"]["title"] == "Done"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_move_task_to_group_returns_moved_item(
    mock_client: AsyncMock,
    monday_move_item_response: dict[str, Any],
) -> None:
    """move_task_to_group() returns the item data with its new group."""
    expected = monday_move_item_response["data"]["move_item_to_group"]
    mock_client.move_item_to_group.return_value = expected

    result = await move_task_to_group(item_id=111, group_id="group_3")

    assert result["group"]["id"] == "group_3"
    assert result["name"] == "Implement auth service"
