"""End-to-end workflow tests for Monday-for-Agents.

These scenario tests simulate complete multi-step workflows through the
system.  Both the LLM and the Monday.com API are mocked so that the
tests are deterministic, fast, and require no external services.

The point is to verify that the *plumbing* works end-to-end: tool
registration, argument serialisation, response parsing, and state
transitions all happen correctly when the components are wired together.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

import monday_mcp.client as client_module
from monday_mcp.client import MONDAY_API_URL
from monday_mcp.tools.boards import get_board_summary
from monday_mcp.tools.items import create_task, get_my_tasks, get_task_details, update_task_status
from monday_mcp.tools.subitems import create_subtask
from monday_mcp.tools.updates import add_task_comment
from a2a_server.models import (
    A2AConfig,
    A2ASkill,
    AgentDefinition,
    AgentMetadata,
    LLMConfig,
    MondayConfig,
    PromptConfig,
    ToolsConfig,
)
from a2a_server.registry import AgentRegistry, make_a2a_send_tool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the MondayClient singleton for each test."""
    client_module._client = None


def _make_agent_def(name: str, port: int) -> AgentDefinition:
    """Create a minimal agent definition."""
    return AgentDefinition(
        metadata=AgentMetadata(name=name, display_name=name.title(), description=f"{name} agent"),
        a2a=A2AConfig(port=port, skills=[A2ASkill(id="work", name="Work", description="work")]),
        llm=LLMConfig(),
        tools=ToolsConfig(),
        monday=MondayConfig(board_id="123456789"),
        prompt=PromptConfig(system=f"You are {name}."),
    )


# ---------------------------------------------------------------------------
# Monday API response factories for E2E scenarios
# ---------------------------------------------------------------------------


def _create_item_resp(item_id: str, name: str, group_id: str = "topics") -> dict[str, Any]:
    """Build a create_item API response."""
    return {
        "data": {
            "create_item": {
                "id": item_id,
                "name": name,
                "group": {"id": group_id, "title": "To Do"},
                "column_values": [
                    {"id": "status", "type": "status", "text": "To Do", "value": '{"index":0}'},
                    {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                ],
            }
        }
    }


def _create_update_resp(update_id: str = "upd-1") -> dict[str, Any]:
    """Build a create_update API response."""
    return {
        "data": {
            "create_update": {
                "id": update_id,
                "body": "<p>comment</p>",
                "created_at": "2025-06-01T12:00:00Z",
            }
        }
    }


def _change_columns_resp(item_id: str, status: str) -> dict[str, Any]:
    """Build a change_multiple_column_values API response."""
    return {
        "data": {
            "change_multiple_column_values": {
                "id": item_id,
                "name": "Task",
                "column_values": [
                    {"id": "status", "type": "status", "text": status, "value": "{}"},
                ],
            }
        }
    }


def _get_items_resp(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a get_items (items_page) response."""
    return {
        "data": {
            "boards": [
                {
                    "items_page": {
                        "cursor": None,
                        "items": items,
                    }
                }
            ]
        }
    }


def _get_item_detail_resp(
    item_id: str,
    name: str,
    status: str = "In Progress",
    updates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a get_item detail response."""
    return {
        "data": {
            "items": [
                {
                    "id": item_id,
                    "name": name,
                    "group": {"id": "group_1", "title": "In Progress"},
                    "board": {"id": "123456789", "name": "Agent Tasks"},
                    "column_values": [
                        {"id": "status", "type": "status", "text": status, "value": "{}"},
                        {"id": "priority", "type": "status", "text": "High", "value": "{}"},
                        {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                    ],
                    "subitems": [],
                    "updates": updates or [],
                }
            ]
        }
    }


def _get_board_resp() -> dict[str, Any]:
    """Build a board metadata response."""
    return {
        "data": {
            "boards": [
                {
                    "id": "123456789",
                    "name": "Agent Tasks",
                    "description": "Task board",
                    "groups": [
                        {"id": "topics", "title": "To Do", "color": "#579bfc"},
                        {"id": "group_1", "title": "In Progress", "color": "#fdab3d"},
                    ],
                    "columns": [],
                }
            ]
        }
    }


def _move_item_resp(item_id: str, group_id: str, group_title: str) -> dict[str, Any]:
    """Build a move_item_to_group response."""
    return {
        "data": {
            "move_item_to_group": {
                "id": item_id,
                "name": "Task",
                "group": {"id": group_id, "title": group_title},
            }
        }
    }


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.e2e
class TestProductOwnerWorkflow:
    """PO workflow: receive feature request, create tasks, delegate."""

    async def test_po_creates_tasks_for_feature_request(self) -> None:
        """PO breaks a feature into tasks and creates them on the board.

        Simulates: receive "Build user auth" -> create 3 tasks -> add
        descriptions as comments.
        """
        responses = [
            # Task 1: create_item
            _create_item_resp("101", "Set up auth service"),
            # Task 1: create_update (description)
            _create_update_resp("upd-101"),
            # Task 2: create_item
            _create_item_resp("102", "Implement login endpoint"),
            # Task 2: create_update (description)
            _create_update_resp("upd-102"),
            # Task 3: create_item
            _create_item_resp("103", "Add JWT token handling"),
            # Task 3: create_update (description)
            _create_update_resp("upd-103"),
        ]
        call_idx = 0

        def _respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            return httpx.Response(200, json=resp)

        with respx.mock(base_url=MONDAY_API_URL) as router:
            router.post("").mock(side_effect=_respond)

            # Simulate PO creating three tasks
            tasks_created = []
            for name, desc in [
                ("Set up auth service", "Configure auth service infrastructure"),
                ("Implement login endpoint", "POST /api/login with email+password"),
                ("Add JWT token handling", "Issue and validate JWT tokens"),
            ]:
                result = await create_task(
                    board_id=123456789,
                    group_id="topics",
                    name=name,
                    status="To Do",
                    assignee="developer",
                    priority="High",
                    task_type="Feature",
                    description=desc,
                    context_id="ctx-auth",
                )
                tasks_created.append(result)

            assert len(tasks_created) == 3
            assert tasks_created[0]["id"] == "101"
            assert tasks_created[1]["id"] == "102"
            assert tasks_created[2]["id"] == "103"

            # 3 create_item + 3 create_update = 6 calls
            assert router.calls.call_count == 6


@pytest.mark.e2e
class TestDeveloperWorkflow:
    """Developer workflow: read task, update status, submit for review."""

    async def test_developer_works_on_task(self) -> None:
        """Developer reads task, marks In Progress, adds comments, sends to review.

        Flow:
        1. Read task details
        2. Update status to In Progress
        3. Add progress comment
        4. Update status to In Review
        5. Add completion comment
        """
        responses = [
            # 1. get_task_details
            _get_item_detail_resp("111", "Implement auth service"),
            # 2. update_task_status -> In Progress
            _change_columns_resp("111", "In Progress"),
            # 3. add_task_comment (progress)
            _create_update_resp("upd-progress"),
            # 4. update_task_status -> In Review
            _change_columns_resp("111", "In Review"),
            # 4b. add comment alongside status change
            _create_update_resp("upd-complete"),
        ]
        call_idx = 0

        def _respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            return httpx.Response(200, json=resp)

        with respx.mock(base_url=MONDAY_API_URL) as router:
            router.post("").mock(side_effect=_respond)

            # Step 1: Read task
            task = await get_task_details(item_id=111)
            assert task["name"] == "Implement auth service"

            # Step 2: Move to In Progress
            result = await update_task_status(
                board_id=123456789, item_id=111, status="In Progress"
            )
            assert result["id"] == "111"

            # Step 3: Add progress comment
            await add_task_comment(
                item_id=111, body="Starting implementation. Approach: OAuth2 + JWT."
            )

            # Step 4: Move to In Review with comment
            result = await update_task_status(
                board_id=123456789,
                item_id=111,
                status="In Review",
                comment="Implementation complete. Ready for review.",
            )
            assert result["id"] == "111"

            assert router.calls.call_count == 5


@pytest.mark.e2e
class TestReviewerWorkflow:
    """Reviewer workflow: read task, review, approve or reject."""

    async def test_reviewer_approves_task(self) -> None:
        """Reviewer reads task, approves it, and marks as Done.

        Flow:
        1. Read task details (with developer's comments)
        2. Add approval comment
        3. Update status to Done
        """
        dev_updates = [
            {
                "id": "upd-1",
                "body": "<p>Implementation complete.</p>",
                "text_body": "Implementation complete.",
                "created_at": "2025-06-01T12:00:00Z",
                "creator": {"name": "Developer Agent"},
            },
        ]

        responses = [
            # 1. get_task_details
            _get_item_detail_resp("111", "Implement auth service", "In Review", dev_updates),
            # 2. add approval comment
            _create_update_resp("upd-approve"),
            # 3. update status to Done
            _change_columns_resp("111", "Done"),
            # 3b. status update comment
            _create_update_resp("upd-done-comment"),
        ]
        call_idx = 0

        def _respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            return httpx.Response(200, json=resp)

        with respx.mock(base_url=MONDAY_API_URL) as router:
            router.post("").mock(side_effect=_respond)

            # Step 1: Read the task
            task = await get_task_details(item_id=111)
            assert len(task["updates"]) == 1
            assert "Implementation complete" in task["updates"][0]["text_body"]

            # Step 2: Add approval comment
            await add_task_comment(
                item_id=111,
                body="Approved. Implementation looks good. Clean approach with JWT.",
            )

            # Step 3: Mark as Done
            await update_task_status(
                board_id=123456789,
                item_id=111,
                status="Done",
                comment="Task approved and completed.",
            )

            assert router.calls.call_count == 4


@pytest.mark.e2e
class TestFullLifecycle:
    """Full lifecycle: PO creates -> Dev works -> Reviewer approves."""

    async def test_complete_task_lifecycle(self) -> None:
        """A task goes through its complete lifecycle across all three agents.

        Simulates the full chain:
        1. PO creates a task
        2. Developer reads and starts working
        3. Developer finishes and sends to review
        4. Reviewer reads, approves, and marks Done
        """
        responses = [
            # === PO Phase ===
            # 1. PO creates task
            _create_item_resp("200", "Build login page"),
            # 2. PO adds description
            _create_update_resp("upd-desc"),
            # === Developer Phase ===
            # 3. Dev reads task
            _get_item_detail_resp("200", "Build login page", "To Do"),
            # 4. Dev updates to In Progress
            _change_columns_resp("200", "In Progress"),
            # 5. Dev adds progress comment
            _create_update_resp("upd-dev-start"),
            # 6. Dev updates to In Review + comment
            _change_columns_resp("200", "In Review"),
            _create_update_resp("upd-dev-done"),
            # === Reviewer Phase ===
            # 7. Reviewer reads task
            _get_item_detail_resp(
                "200",
                "Build login page",
                "In Review",
                [
                    {
                        "id": "upd-dev-done",
                        "body": "<p>Login page implemented with React.</p>",
                        "text_body": "Login page implemented with React.",
                        "created_at": "2025-06-01T14:00:00Z",
                        "creator": {"name": "Developer Agent"},
                    },
                ],
            ),
            # 8. Reviewer adds approval comment
            _create_update_resp("upd-approve"),
            # 9. Reviewer marks Done + comment
            _change_columns_resp("200", "Done"),
            _create_update_resp("upd-final"),
        ]
        call_idx = 0

        def _respond(request: httpx.Request) -> httpx.Response:
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            return httpx.Response(200, json=resp)

        with respx.mock(base_url=MONDAY_API_URL) as router:
            router.post("").mock(side_effect=_respond)

            # --- PO Phase ---
            po_task = await create_task(
                board_id=123456789,
                group_id="topics",
                name="Build login page",
                status="To Do",
                assignee="developer",
                priority="High",
                task_type="Feature",
                description="Create a responsive login page with email/password form.",
            )
            assert po_task["id"] == "200"

            # --- Developer Phase ---
            task = await get_task_details(item_id=200)
            assert task["name"] == "Build login page"

            await update_task_status(
                board_id=123456789, item_id=200, status="In Progress"
            )

            await add_task_comment(
                item_id=200,
                body="Starting work. Will use React with form validation.",
            )

            await update_task_status(
                board_id=123456789,
                item_id=200,
                status="In Review",
                comment="Implementation complete. Login page ready for review.",
            )

            # --- Reviewer Phase ---
            task_for_review = await get_task_details(item_id=200)
            assert len(task_for_review["updates"]) == 1

            await add_task_comment(
                item_id=200,
                body="LGTM. Clean implementation with good validation.",
            )

            await update_task_status(
                board_id=123456789,
                item_id=200,
                status="Done",
                comment="Approved and completed.",
            )

            # Total: 2 (PO) + 5 (Dev) + 4 (Reviewer) = 11 API calls
            assert router.calls.call_count == 11


@pytest.mark.e2e
class TestMultiAgentDelegation:
    """Test inter-agent delegation via the A2A send_message tool."""

    async def test_po_delegates_to_developer(self) -> None:
        """PO creates tasks then sends A2A message to developer.

        This tests the full delegation flow: task creation on Monday.com
        followed by inter-agent notification via A2A JSON-RPC.
        """
        registry = AgentRegistry()
        registry.register(_make_agent_def("product-owner", 10001))
        registry.register(_make_agent_def("developer", 10002))
        send_tool = make_a2a_send_tool(registry)

        # Mock Monday API for task creation
        monday_responses = [
            _create_item_resp("300", "Implement feature X"),
            _create_update_resp("upd-300"),
        ]
        monday_idx = 0

        def _monday_respond(request: httpx.Request) -> httpx.Response:
            nonlocal monday_idx
            resp = monday_responses[monday_idx]
            monday_idx += 1
            return httpx.Response(200, json=resp)

        with respx.mock:
            respx.post(MONDAY_API_URL).mock(side_effect=_monday_respond)

            # PO creates task
            task = await create_task(
                board_id=123456789,
                group_id="topics",
                name="Implement feature X",
                assignee="developer",
                description="Build feature X as specified in the PRD.",
            )
            assert task["id"] == "300"

            # PO sends A2A message to developer
            respx.post("http://localhost:10002").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "artifacts": [
                                {
                                    "parts": [
                                        {
                                            "kind": "text",
                                            "text": "Acknowledged. I will start working on task #300.",
                                        }
                                    ]
                                }
                            ]
                        },
                    },
                )
            )

            delegation_result = await send_tool.ainvoke(
                {
                    "agent_name": "developer",
                    "message": f"New task assigned: 'Implement feature X' (ID: {task['id']}). Please start working on it.",
                }
            )

            assert "acknowledged" in delegation_result.lower()
            assert "300" in delegation_result
