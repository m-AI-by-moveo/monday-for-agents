"""Integration tests for the MCP server tool-to-client-to-API chain.

These tests exercise the full flow from MCP tool functions through the
MondayClient down to the HTTP layer.  Only the external Monday.com API
is mocked (via ``respx``); the internal wiring between tools, client
helpers, and the httpx transport is tested as-is.

Every test resets the module-level ``_client`` singleton so that each
test starts with a fresh ``MondayClient`` whose underlying
``httpx.AsyncClient`` is intercepted by ``respx``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

import monday_mcp.client as client_module
from monday_mcp.client import MONDAY_API_URL, MondayClient
from monday_mcp.tools.boards import get_board_summary
from monday_mcp.tools.items import create_task, get_my_tasks, get_task_details, update_task_status
from monday_mcp.tools.subitems import create_subtask, move_task_to_group
from monday_mcp.tools.updates import add_task_comment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_client_singleton() -> None:
    """Reset the module-level MondayClient singleton before each test.

    This ensures every test gets a fresh client whose httpx transport
    is created under the ``respx`` mock context.
    """
    client_module._client = None


@pytest.fixture()
def mock_monday_api() -> respx.MockRouter:
    """Activate a ``respx`` router that intercepts all calls to MONDAY_API_URL.

    The caller is responsible for adding routes via
    ``mock_monday_api.post(...).respond(...)``.
    """
    with respx.mock(base_url=MONDAY_API_URL) as router:
        yield router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graphql_response(data: dict[str, Any]) -> httpx.Response:
    """Build an ``httpx.Response`` wrapping a Monday.com-style JSON body."""
    return httpx.Response(200, json={"data": data})


def _graphql_side_effect(*ordered_responses: dict[str, Any]):
    """Return a side-effect callable that yields ordered GraphQL responses.

    Useful when a single test needs multiple sequential API calls (e.g.
    create_item followed by create_update).
    """
    responses = list(ordered_responses)
    call_index = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_index
        if call_index < len(responses):
            resp = responses[call_index]
            call_index += 1
            return _graphql_response(resp)
        pytest.fail(f"Unexpected extra API call (call #{call_index + 1})")

    return _side_effect


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.integration
class TestCreateTask:
    """create_task flows through items.py -> client.py -> mock Monday API."""

    async def test_create_task_minimal(
        self,
        mock_monday_api: respx.MockRouter,
        monday_create_item_response: dict[str, Any],
    ) -> None:
        """Creating a task with only required fields issues one API call."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_create_item_response)
        )

        result = await create_task(
            board_id=123456789,
            group_id="topics",
            name="New task",
        )

        assert result["id"] == "666"
        assert result["name"] == "New task"
        assert mock_monday_api.calls.call_count == 1

    async def test_create_task_with_description(
        self,
        mock_monday_api: respx.MockRouter,
        monday_create_item_response: dict[str, Any],
        monday_create_update_response: dict[str, Any],
    ) -> None:
        """A description triggers a second API call (create_update)."""
        mock_monday_api.post("").mock(
            side_effect=_graphql_side_effect(
                monday_create_item_response["data"],
                monday_create_update_response["data"],
            )
        )

        result = await create_task(
            board_id=123456789,
            group_id="topics",
            name="New task",
            description="Acceptance criteria: ...",
        )

        assert result["id"] == "666"
        # Two calls: create_item + create_update
        assert mock_monday_api.calls.call_count == 2

    async def test_create_task_with_all_columns(
        self,
        mock_monday_api: respx.MockRouter,
        monday_create_item_response: dict[str, Any],
    ) -> None:
        """All optional column values are sent in the create_item mutation."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_create_item_response)
        )

        result = await create_task(
            board_id=123456789,
            group_id="topics",
            name="Auth feature",
            status="To Do",
            assignee="developer",
            priority="High",
            task_type="Feature",
            context_id="ctx-123",
        )

        assert result["id"] == "666"

        # Verify the payload sent to the API contains column values
        sent_body = json.loads(mock_monday_api.calls.last.request.content)
        variables = sent_body["variables"]
        assert "columnValues" in variables
        col_vals = json.loads(variables["columnValues"])
        assert col_vals["status"] == {"label": "To Do"}
        assert col_vals["priority"] == {"label": "High"}
        assert col_vals["text"] == "developer"
        assert col_vals["dropdown"] == {"labels": ["Feature"]}
        assert col_vals["text0"] == "ctx-123"


@pytest.mark.integration
class TestUpdateTaskStatus:
    """update_task_status flows correctly with status change and comment."""

    async def test_update_status_only(
        self,
        mock_monday_api: respx.MockRouter,
        monday_change_columns_response: dict[str, Any],
    ) -> None:
        """Updating status without a comment issues one API call."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_change_columns_response)
        )

        result = await update_task_status(
            board_id=123456789,
            item_id=111,
            status="Done",
        )

        assert result["id"] == "111"
        assert mock_monday_api.calls.call_count == 1

    async def test_update_status_with_comment(
        self,
        mock_monday_api: respx.MockRouter,
        monday_change_columns_response: dict[str, Any],
        monday_create_update_response: dict[str, Any],
    ) -> None:
        """Updating status with a comment issues two API calls."""
        mock_monday_api.post("").mock(
            side_effect=_graphql_side_effect(
                monday_change_columns_response["data"],
                monday_create_update_response["data"],
            )
        )

        result = await update_task_status(
            board_id=123456789,
            item_id=111,
            status="Done",
            comment="All work complete.",
        )

        assert result["id"] == "111"
        assert mock_monday_api.calls.call_count == 2

    async def test_update_status_invalid_raises(
        self,
        mock_monday_api: respx.MockRouter,
    ) -> None:
        """An invalid status value raises ValueError before any API call."""
        with pytest.raises(ValueError, match="Invalid status"):
            await update_task_status(
                board_id=123456789,
                item_id=111,
                status="InvalidStatus",
            )

        assert mock_monday_api.calls.call_count == 0


@pytest.mark.integration
class TestGetMyTasks:
    """get_my_tasks correctly paginates and filters by assignee."""

    async def test_single_page(
        self,
        mock_monday_api: respx.MockRouter,
        monday_items_response: dict[str, Any],
    ) -> None:
        """Single-page board returns filtered items for matching assignee."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_items_response)
        )

        tasks = await get_my_tasks(board_id=123456789, assignee="developer")

        # Items 111 and 222 are assigned to "developer"
        assert len(tasks) == 2
        names = {t["name"] for t in tasks}
        assert "Implement auth service" in names
        assert "Write API tests" in names

    async def test_pagination(
        self,
        mock_monday_api: respx.MockRouter,
    ) -> None:
        """Multi-page results are followed until cursor is None."""
        page1 = {
            "data": {
                "boards": [
                    {
                        "items_page": {
                            "cursor": "cursor-page-2",
                            "items": [
                                {
                                    "id": "10",
                                    "name": "Task A",
                                    "group": {"id": "topics", "title": "To Do"},
                                    "column_values": [
                                        {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                                    ],
                                },
                            ],
                        }
                    }
                ]
            }
        }
        page2 = {
            "data": {
                "boards": [
                    {
                        "items_page": {
                            "cursor": None,
                            "items": [
                                {
                                    "id": "20",
                                    "name": "Task B",
                                    "group": {"id": "topics", "title": "To Do"},
                                    "column_values": [
                                        {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                                    ],
                                },
                            ],
                        }
                    }
                ]
            }
        }

        responses = [page1, page2]
        idx = 0

        def _respond(request: httpx.Request) -> httpx.Response:
            nonlocal idx
            resp = responses[idx]
            idx += 1
            return httpx.Response(200, json=resp)

        mock_monday_api.post("").mock(side_effect=_respond)

        tasks = await get_my_tasks(board_id=123456789, assignee="developer")

        assert len(tasks) == 2
        assert tasks[0]["id"] == "10"
        assert tasks[1]["id"] == "20"
        assert mock_monday_api.calls.call_count == 2

    async def test_case_insensitive_filter(
        self,
        mock_monday_api: respx.MockRouter,
        monday_items_response: dict[str, Any],
    ) -> None:
        """Assignee matching is case-insensitive."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_items_response)
        )

        tasks = await get_my_tasks(board_id=123456789, assignee="Developer")
        assert len(tasks) == 2

    async def test_no_matches(
        self,
        mock_monday_api: respx.MockRouter,
        monday_items_response: dict[str, Any],
    ) -> None:
        """Requesting an assignee with no matching tasks returns empty list."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_items_response)
        )

        tasks = await get_my_tasks(board_id=123456789, assignee="nonexistent-agent")
        assert tasks == []


@pytest.mark.integration
class TestGetBoardSummary:
    """get_board_summary processes multi-page boards correctly."""

    async def test_single_page_board(
        self,
        mock_monday_api: respx.MockRouter,
        monday_board_response: dict[str, Any],
        monday_items_response: dict[str, Any],
    ) -> None:
        """A single-page board returns correct summary with status grouping."""
        mock_monday_api.post("").mock(
            side_effect=_graphql_side_effect(
                monday_board_response["data"],
                monday_items_response["data"],
            )
        )

        summary = await get_board_summary(board_id=123456789)

        assert summary["board_name"] == "Agent Tasks"
        assert summary["total_items"] == 3
        assert "In Progress" in summary["by_status"]
        assert "To Do" in summary["by_status"]
        assert "In Review" in summary["by_status"]
        assert len(summary["by_status"]["In Progress"]) == 1
        assert summary["by_status"]["In Progress"][0]["name"] == "Implement auth service"

    async def test_multi_page_board(
        self,
        mock_monday_api: respx.MockRouter,
        monday_board_response: dict[str, Any],
    ) -> None:
        """Multi-page boards accumulate items across pages."""
        page1 = {
            "boards": [
                {
                    "items_page": {
                        "cursor": "next",
                        "items": [
                            {
                                "id": "1",
                                "name": "Task 1",
                                "group": {"id": "topics", "title": "To Do"},
                                "column_values": [
                                    {"id": "status", "type": "status", "text": "To Do"},
                                    {"id": "text", "type": "text", "text": "dev"},
                                    {"id": "priority", "type": "status", "text": "High"},
                                ],
                            },
                        ],
                    }
                }
            ]
        }
        page2 = {
            "boards": [
                {
                    "items_page": {
                        "cursor": None,
                        "items": [
                            {
                                "id": "2",
                                "name": "Task 2",
                                "group": {"id": "group_1", "title": "In Progress"},
                                "column_values": [
                                    {"id": "status", "type": "status", "text": "In Progress"},
                                    {"id": "text", "type": "text", "text": "dev"},
                                    {"id": "priority", "type": "status", "text": "Medium"},
                                ],
                            },
                        ],
                    }
                }
            ]
        }

        mock_monday_api.post("").mock(
            side_effect=_graphql_side_effect(
                monday_board_response["data"],
                page1,
                page2,
            )
        )

        summary = await get_board_summary(board_id=123456789)

        assert summary["total_items"] == 2
        assert len(summary["by_status"]) == 2
        assert "To Do" in summary["by_status"]
        assert "In Progress" in summary["by_status"]


@pytest.mark.integration
class TestGetTaskDetails:
    """get_task_details returns complete item with subitems and updates."""

    async def test_full_item_details(
        self,
        mock_monday_api: respx.MockRouter,
        monday_item_detail_response: dict[str, Any],
    ) -> None:
        """The tool returns the full item including subitems and updates."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_item_detail_response)
        )

        item = await get_task_details(item_id=111)

        assert item["id"] == "111"
        assert item["name"] == "Implement auth service"
        assert len(item["subitems"]) == 2
        assert item["subitems"][0]["name"] == "Set up JWT tokens"
        assert len(item["updates"]) == 2
        assert "JWT token setup complete" in item["updates"][1]["text_body"]
        assert item["board"]["name"] == "Agent Tasks"

    async def test_item_column_values(
        self,
        mock_monday_api: respx.MockRouter,
        monday_item_detail_response: dict[str, Any],
    ) -> None:
        """Column values are included in the returned item."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_item_detail_response)
        )

        item = await get_task_details(item_id=111)

        col_map = {c["id"]: c for c in item["column_values"]}
        assert col_map["status"]["text"] == "In Progress"
        assert col_map["priority"]["text"] == "High"
        assert col_map["text"]["text"] == "developer"


@pytest.mark.integration
class TestAddTaskComment:
    """add_task_comment through the full chain."""

    async def test_add_comment(
        self,
        mock_monday_api: respx.MockRouter,
        monday_create_update_response: dict[str, Any],
    ) -> None:
        """Adding a comment issues a create_update mutation."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_create_update_response)
        )

        result = await add_task_comment(item_id=111, body="Progress update: 50% done")

        assert result["id"] == "upd_new"
        assert mock_monday_api.calls.call_count == 1

        # Verify the body was sent correctly
        sent = json.loads(mock_monday_api.calls.last.request.content)
        assert "Progress update: 50% done" in sent["variables"]["body"]

    async def test_empty_comment_raises(
        self,
        mock_monday_api: respx.MockRouter,
    ) -> None:
        """An empty comment body raises ValueError before any API call."""
        with pytest.raises(ValueError, match="must not be empty"):
            await add_task_comment(item_id=111, body="")

        assert mock_monday_api.calls.call_count == 0

    async def test_whitespace_only_comment_raises(
        self,
        mock_monday_api: respx.MockRouter,
    ) -> None:
        """A whitespace-only comment body raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            await add_task_comment(item_id=111, body="   ")

        assert mock_monday_api.calls.call_count == 0


@pytest.mark.integration
class TestCreateSubtask:
    """create_subtask with column values."""

    async def test_create_subtask_minimal(
        self,
        mock_monday_api: respx.MockRouter,
        monday_create_subitem_response: dict[str, Any],
    ) -> None:
        """Creating a subtask with only required fields works."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_create_subitem_response)
        )

        result = await create_subtask(parent_item_id=111, name="New subtask")

        assert result["id"] == "777"
        assert result["name"] == "New subtask"
        assert mock_monday_api.calls.call_count == 1

    async def test_create_subtask_with_columns(
        self,
        mock_monday_api: respx.MockRouter,
        monday_create_subitem_response: dict[str, Any],
    ) -> None:
        """Column values (status, assignee) are passed through."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_create_subitem_response)
        )

        result = await create_subtask(
            parent_item_id=111,
            name="Sub with columns",
            status="In Progress",
            assignee="developer",
        )

        assert result["id"] == "777"

        # Verify column values were sent
        sent = json.loads(mock_monday_api.calls.last.request.content)
        col_vals = json.loads(sent["variables"]["columnValues"])
        assert col_vals["status"] == {"label": "In Progress"}
        assert col_vals["text"] == "developer"

    async def test_create_subtask_invalid_status(
        self,
        mock_monday_api: respx.MockRouter,
    ) -> None:
        """Invalid status raises ValueError before API call."""
        with pytest.raises(ValueError, match="Invalid status"):
            await create_subtask(
                parent_item_id=111,
                name="Bad subtask",
                status="NotAStatus",
            )

        assert mock_monday_api.calls.call_count == 0


@pytest.mark.integration
class TestMoveTaskToGroup:
    """move_task_to_group sends correct mutation."""

    async def test_move_item(
        self,
        mock_monday_api: respx.MockRouter,
        monday_move_item_response: dict[str, Any],
    ) -> None:
        """Moving an item issues the move_item_to_group mutation."""
        mock_monday_api.post("").mock(
            return_value=httpx.Response(200, json=monday_move_item_response)
        )

        result = await move_task_to_group(item_id=111, group_id="group_3")

        assert result["id"] == "111"
        assert result["group"]["id"] == "group_3"
        assert result["group"]["title"] == "Done"
        assert mock_monday_api.calls.call_count == 1

        # Verify the variables sent
        sent = json.loads(mock_monday_api.calls.last.request.content)
        assert sent["variables"]["itemId"] == "111"
        assert sent["variables"]["groupId"] == "group_3"
