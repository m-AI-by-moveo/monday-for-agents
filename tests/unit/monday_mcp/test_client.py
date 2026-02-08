"""Tests for the MondayClient class and module-level singleton."""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx

import monday_mcp.client
from monday_mcp.client import (
    MONDAY_API_URL,
    MondayAPIError,
    MondayClient,
    _RATE_LIMIT_POINTS_PER_MIN,
    get_client,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton() -> Any:
    """Reset the module-level client singleton between tests."""
    monday_mcp.client._client = None
    yield
    monday_mcp.client._client = None


@pytest.fixture()
def client() -> MondayClient:
    """Return a fresh MondayClient configured with the test token."""
    return MondayClient(api_token="test-token-do-not-use")


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_init_from_explicit_token() -> None:
    """MondayClient can be initialised with an explicit API token."""
    c = MondayClient(api_token="my-token")
    assert c._token == "my-token"


@pytest.mark.unit
def test_init_from_env_var() -> None:
    """MondayClient falls back to the MONDAY_API_TOKEN env var."""
    # The autouse _mock_env fixture sets MONDAY_API_TOKEN="test-token-do-not-use"
    c = MondayClient()
    assert c._token == "test-token-do-not-use"


@pytest.mark.unit
def test_init_raises_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """MondayClient raises ValueError when no token is available."""
    monkeypatch.delenv("MONDAY_API_TOKEN", raising=False)
    with pytest.raises(ValueError, match="MONDAY_API_TOKEN"):
        MondayClient()


# ---------------------------------------------------------------------------
# execute()
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_execute_returns_data_on_success(client: MondayClient) -> None:
    """execute() returns the 'data' portion of a successful response."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"boards": [{"id": "1"}]}},
        )
    )
    result = await client.execute("query { boards { id } }")
    assert result == {"boards": [{"id": "1"}]}


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_execute_raises_monday_api_error_on_errors_field(
    client: MondayClient,
) -> None:
    """execute() raises MondayAPIError when the response contains 'errors'."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "errors": [{"message": "Column not found"}],
                "data": None,
            },
        )
    )
    with pytest.raises(MondayAPIError, match="Column not found"):
        await client.execute("mutation { ... }")


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_execute_raises_monday_api_error_on_error_message_field(
    client: MondayClient,
) -> None:
    """execute() raises MondayAPIError when the response has an 'error_message' field."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"error_message": "Authentication failed"},
        )
    )
    with pytest.raises(MondayAPIError, match="Authentication failed"):
        await client.execute("query { me { id } }")


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_execute_raises_on_http_error(client: MondayClient) -> None:
    """execute() raises httpx.HTTPStatusError on non-2xx responses."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(500, json={"error": "Internal Server Error"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await client.execute("query { boards { id } }")


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_execute_sends_variables(client: MondayClient) -> None:
    """execute() includes variables in the request payload."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json={"data": {"boards": []}})
    )
    await client.execute("query ($id: ID!) { boards(ids: [$id]) { id } }", {"id": "42"})

    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"] == {"id": "42"}


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_execute_tracks_complexity(client: MondayClient) -> None:
    """execute() records complexity points from the response."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {"boards": []},
                "complexity": {"after": 5000},
            },
        )
    )
    await client.execute("query { boards { id } }")
    assert client._complexity_consumed == 5000


# ---------------------------------------------------------------------------
# Board operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_get_board_returns_first_board(
    client: MondayClient,
    monday_board_response: dict[str, Any],
) -> None:
    """get_board() returns the first board from the response."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_board_response)
    )
    board = await client.get_board(123456789)
    assert board["id"] == "123456789"
    assert board["name"] == "Agent Tasks"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_get_board_raises_when_not_found(client: MondayClient) -> None:
    """get_board() raises MondayAPIError when board is not found."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"boards": []}},
        )
    )
    with pytest.raises(MondayAPIError, match="Board 999 not found"):
        await client.get_board(999)


# ---------------------------------------------------------------------------
# Item operations
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_get_items_returns_items_page_with_cursor(
    client: MondayClient,
    monday_items_response: dict[str, Any],
) -> None:
    """get_items() returns the items_page dict with cursor and items."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_items_response)
    )
    page = await client.get_items(123456789)
    assert page["cursor"] is None
    assert len(page["items"]) == 3
    assert page["items"][0]["name"] == "Implement auth service"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_get_item_returns_item_details(
    client: MondayClient,
    monday_item_detail_response: dict[str, Any],
) -> None:
    """get_item() returns the full item with subitems and updates."""
    respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_item_detail_response)
    )
    item = await client.get_item(111)
    assert item["id"] == "111"
    assert len(item["subitems"]) == 2
    assert len(item["updates"]) == 2


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_create_item_sends_correct_variables(
    client: MondayClient,
    monday_create_item_response: dict[str, Any],
) -> None:
    """create_item() sends the correct GraphQL variables."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_create_item_response)
    )
    column_vals = {"status": {"label": "To Do"}}
    result = await client.create_item(
        board_id=123456789,
        group_id="topics",
        item_name="New task",
        column_values=column_vals,
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"]["boardId"] == "123456789"
    assert sent["variables"]["groupId"] == "topics"
    assert sent["variables"]["itemName"] == "New task"
    assert sent["variables"]["columnValues"] == json.dumps(column_vals)
    assert result["id"] == "666"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_change_column_values_json_encodes(
    client: MondayClient,
    monday_change_columns_response: dict[str, Any],
) -> None:
    """change_column_values() JSON-encodes the column_values parameter."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_change_columns_response)
    )
    cols = {"status": {"label": "Done"}}
    await client.change_column_values(
        item_id=111,
        board_id=123456789,
        column_values=cols,
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"]["columnValues"] == json.dumps(cols)
    assert sent["variables"]["itemId"] == "111"
    assert sent["variables"]["boardId"] == "123456789"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_create_update_sends_correct_body(
    client: MondayClient,
    monday_create_update_response: dict[str, Any],
) -> None:
    """create_update() sends the correct item ID and body."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_create_update_response)
    )
    result = await client.create_update(item_id=111, body="Test comment")

    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"]["itemId"] == "111"
    assert sent["variables"]["body"] == "Test comment"
    assert result["id"] == "upd_new"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_create_subitem_with_column_values(
    client: MondayClient,
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """create_subitem() sends column_values when provided."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_create_subitem_response)
    )
    cols = {"status": {"label": "To Do"}}
    result = await client.create_subitem(
        parent_item_id=111,
        item_name="New subtask",
        column_values=cols,
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"]["parentItemId"] == "111"
    assert sent["variables"]["itemName"] == "New subtask"
    assert sent["variables"]["columnValues"] == json.dumps(cols)
    assert result["id"] == "777"


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_create_subitem_without_column_values(
    client: MondayClient,
    monday_create_subitem_response: dict[str, Any],
) -> None:
    """create_subitem() omits columnValues when not provided."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_create_subitem_response)
    )
    await client.create_subitem(parent_item_id=111, item_name="Simple subtask")

    sent = json.loads(route.calls[0].request.content)
    assert "columnValues" not in sent["variables"]


@pytest.mark.unit
@pytest.mark.asyncio
@respx.mock
async def test_move_item_to_group_sends_correct_variables(
    client: MondayClient,
    monday_move_item_response: dict[str, Any],
) -> None:
    """move_item_to_group() sends the correct item ID and group ID."""
    route = respx.post(MONDAY_API_URL).mock(
        return_value=httpx.Response(200, json=monday_move_item_response)
    )
    result = await client.move_item_to_group(item_id=111, group_id="group_3")

    sent = json.loads(route.calls[0].request.content)
    assert sent["variables"]["itemId"] == "111"
    assert sent["variables"]["groupId"] == "group_3"
    assert result["group"]["title"] == "Done"


# ---------------------------------------------------------------------------
# Rate-limit tracking
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_rate_limit_resets_after_60_seconds(client: MondayClient) -> None:
    """The rate-limit window resets after 60 seconds elapse."""
    client._complexity_consumed = 5_000_000
    # Simulate 61 seconds passing.
    client._window_start = time.monotonic() - 61
    client._check_rate_limit()
    assert client._complexity_consumed == 0


@pytest.mark.unit
def test_rate_limit_warning_logged_when_near_limit(
    client: MondayClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A warning is logged when complexity nears 90% of the limit."""
    client._complexity_consumed = int(_RATE_LIMIT_POINTS_PER_MIN * 0.91)
    # Window started recently (not yet expired).
    client._window_start = time.monotonic() - 5
    with caplog.at_level("WARNING", logger="monday_mcp.client"):
        client._check_rate_limit()
    assert "rate limit" in caplog.text.lower()


@pytest.mark.unit
def test_rate_limit_no_warning_below_threshold(
    client: MondayClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No warning is logged when complexity is well below the threshold."""
    client._complexity_consumed = 1000
    client._window_start = time.monotonic() - 5
    with caplog.at_level("WARNING", logger="monday_mcp.client"):
        client._check_rate_limit()
    assert "rate limit" not in caplog.text.lower()


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_client_returns_singleton() -> None:
    """get_client() returns the same instance on repeated calls."""
    c1 = get_client()
    c2 = get_client()
    assert c1 is c2


@pytest.mark.unit
def test_get_client_creates_new_after_reset() -> None:
    """get_client() creates a new client after the singleton is reset."""
    c1 = get_client()
    monday_mcp.client._client = None
    c2 = get_client()
    assert c1 is not c2
