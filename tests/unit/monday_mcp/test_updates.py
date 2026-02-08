"""Tests for Monday.com updates (comments) tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monday_mcp.tools.updates import add_task_comment


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
    with patch("monday_mcp.tools.updates.get_client", return_value=mock_client):
        yield


# ---------------------------------------------------------------------------
# add_task_comment()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_task_comment_calls_client_correctly(
    mock_client: AsyncMock,
    monday_create_update_response: dict[str, Any],
) -> None:
    """add_task_comment() delegates to client.create_update with the correct arguments."""
    mock_client.create_update.return_value = (
        monday_create_update_response["data"]["create_update"]
    )

    result = await add_task_comment(item_id=111, body="Great progress!")

    mock_client.create_update.assert_awaited_once_with(
        item_id=111,
        body="Great progress!",
    )
    assert result["id"] == "upd_new"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_task_comment_raises_on_empty_body(
    mock_client: AsyncMock,
) -> None:
    """add_task_comment() raises ValueError when body is an empty string."""
    with pytest.raises(ValueError, match="must not be empty"):
        await add_task_comment(item_id=111, body="")

    mock_client.create_update.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_task_comment_raises_on_whitespace_only_body(
    mock_client: AsyncMock,
) -> None:
    """add_task_comment() raises ValueError when body contains only whitespace."""
    with pytest.raises(ValueError, match="must not be empty"):
        await add_task_comment(item_id=111, body="   \t\n  ")

    mock_client.create_update.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_task_comment_returns_update_data(
    mock_client: AsyncMock,
    monday_create_update_response: dict[str, Any],
) -> None:
    """add_task_comment() returns the update data from the client."""
    expected = monday_create_update_response["data"]["create_update"]
    mock_client.create_update.return_value = expected

    result = await add_task_comment(item_id=111, body="<p>HTML comment</p>")

    assert result["id"] == expected["id"]
    assert result["body"] == expected["body"]
    assert result["created_at"] == expected["created_at"]
