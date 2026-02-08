"""Shared test fixtures for Monday-for-Agents test suite."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
AGENTS_DIR = PROJECT_ROOT / "agents"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Environment setup — prevent accidental real API calls
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set safe default environment variables for all tests."""
    monkeypatch.setenv("MONDAY_API_TOKEN", "test-token-do-not-use")
    monkeypatch.setenv("MONDAY_BOARD_ID", "123456789")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-do-not-use")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test-signing-secret")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test-token")


# ---------------------------------------------------------------------------
# Monday.com API response factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def monday_board_response() -> dict[str, Any]:
    """A realistic Monday.com board response."""
    return {
        "data": {
            "boards": [
                {
                    "id": "123456789",
                    "name": "Agent Tasks",
                    "description": "Task board for AI agent team",
                    "groups": [
                        {"id": "topics", "title": "To Do", "color": "#579bfc"},
                        {"id": "group_1", "title": "In Progress", "color": "#fdab3d"},
                        {"id": "group_2", "title": "In Review", "color": "#a25ddc"},
                        {"id": "group_3", "title": "Done", "color": "#00c875"},
                        {"id": "group_4", "title": "Blocked", "color": "#e2445c"},
                    ],
                    "columns": [
                        {"id": "name", "title": "Name", "type": "name", "settings_str": "{}"},
                        {"id": "status", "title": "Status", "type": "status", "settings_str": "{}"},
                        {"id": "priority", "title": "Priority", "type": "status", "settings_str": "{}"},
                        {"id": "text", "title": "Assignee", "type": "text", "settings_str": "{}"},
                        {"id": "dropdown", "title": "Type", "type": "dropdown", "settings_str": "{}"},
                        {"id": "text0", "title": "Context ID", "type": "text", "settings_str": "{}"},
                    ],
                }
            ]
        }
    }


@pytest.fixture()
def monday_items_response() -> dict[str, Any]:
    """A realistic Monday.com items page response."""
    return {
        "data": {
            "boards": [
                {
                    "items_page": {
                        "cursor": None,
                        "items": [
                            {
                                "id": "111",
                                "name": "Implement auth service",
                                "group": {"id": "group_1", "title": "In Progress"},
                                "column_values": [
                                    {"id": "status", "type": "status", "text": "In Progress", "value": '{"index":1}'},
                                    {"id": "priority", "type": "status", "text": "High", "value": '{"index":4}'},
                                    {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                                    {"id": "dropdown", "type": "dropdown", "text": "Feature", "value": '{"ids":[0]}'},
                                    {"id": "text0", "type": "text", "text": "ctx-abc-123", "value": '"ctx-abc-123"'},
                                ],
                            },
                            {
                                "id": "222",
                                "name": "Write API tests",
                                "group": {"id": "topics", "title": "To Do"},
                                "column_values": [
                                    {"id": "status", "type": "status", "text": "To Do", "value": '{"index":0}'},
                                    {"id": "priority", "type": "status", "text": "Medium", "value": '{"index":1}'},
                                    {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                                    {"id": "dropdown", "type": "dropdown", "text": "Chore", "value": '{"ids":[2]}'},
                                    {"id": "text0", "type": "text", "text": "", "value": '""'},
                                ],
                            },
                            {
                                "id": "333",
                                "name": "Review auth PR",
                                "group": {"id": "group_2", "title": "In Review"},
                                "column_values": [
                                    {"id": "status", "type": "status", "text": "In Review", "value": '{"index":4}'},
                                    {"id": "priority", "type": "status", "text": "High", "value": '{"index":4}'},
                                    {"id": "text", "type": "text", "text": "reviewer", "value": '"reviewer"'},
                                    {"id": "dropdown", "type": "dropdown", "text": "Feature", "value": '{"ids":[0]}'},
                                    {"id": "text0", "type": "text", "text": "ctx-abc-123", "value": '"ctx-abc-123"'},
                                ],
                            },
                        ],
                    }
                }
            ]
        }
    }


@pytest.fixture()
def monday_item_detail_response() -> dict[str, Any]:
    """A realistic single-item detail response with subitems and updates."""
    return {
        "data": {
            "items": [
                {
                    "id": "111",
                    "name": "Implement auth service",
                    "group": {"id": "group_1", "title": "In Progress"},
                    "board": {"id": "123456789", "name": "Agent Tasks"},
                    "column_values": [
                        {"id": "status", "type": "status", "text": "In Progress", "value": '{"index":1}'},
                        {"id": "priority", "type": "status", "text": "High", "value": '{"index":4}'},
                        {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                        {"id": "dropdown", "type": "dropdown", "text": "Feature", "value": '{"ids":[0]}'},
                        {"id": "text0", "type": "text", "text": "ctx-abc-123", "value": '"ctx-abc-123"'},
                    ],
                    "subitems": [
                        {
                            "id": "444",
                            "name": "Set up JWT tokens",
                            "column_values": [
                                {"id": "status", "type": "status", "text": "Done", "value": '{"index":5}'},
                            ],
                        },
                        {
                            "id": "555",
                            "name": "Implement login endpoint",
                            "column_values": [
                                {"id": "status", "type": "status", "text": "In Progress", "value": '{"index":1}'},
                            ],
                        },
                    ],
                    "updates": [
                        {
                            "id": "upd_1",
                            "body": "<p>Starting implementation of auth service.</p>",
                            "text_body": "Starting implementation of auth service.",
                            "created_at": "2025-06-01T10:00:00Z",
                            "creator": {"name": "Developer Agent"},
                        },
                        {
                            "id": "upd_2",
                            "body": "<p>JWT token setup complete. Moving to login endpoint.</p>",
                            "text_body": "JWT token setup complete. Moving to login endpoint.",
                            "created_at": "2025-06-01T11:30:00Z",
                            "creator": {"name": "Developer Agent"},
                        },
                    ],
                }
            ]
        }
    }


@pytest.fixture()
def monday_create_item_response() -> dict[str, Any]:
    """Response from creating a new item."""
    return {
        "data": {
            "create_item": {
                "id": "666",
                "name": "New task",
                "group": {"id": "topics", "title": "To Do"},
                "column_values": [
                    {"id": "status", "type": "status", "text": "To Do", "value": '{"index":0}'},
                    {"id": "text", "type": "text", "text": "developer", "value": '"developer"'},
                ],
            }
        }
    }


@pytest.fixture()
def monday_create_update_response() -> dict[str, Any]:
    """Response from creating an update (comment)."""
    return {
        "data": {
            "create_update": {
                "id": "upd_new",
                "body": "<p>Test comment</p>",
                "created_at": "2025-06-01T12:00:00Z",
            }
        }
    }


@pytest.fixture()
def monday_create_subitem_response() -> dict[str, Any]:
    """Response from creating a subitem."""
    return {
        "data": {
            "create_subitem": {
                "id": "777",
                "name": "New subtask",
                "column_values": [],
            }
        }
    }


@pytest.fixture()
def monday_move_item_response() -> dict[str, Any]:
    """Response from moving an item to a group."""
    return {
        "data": {
            "move_item_to_group": {
                "id": "111",
                "name": "Implement auth service",
                "group": {"id": "group_3", "title": "Done"},
            }
        }
    }


@pytest.fixture()
def monday_change_columns_response() -> dict[str, Any]:
    """Response from changing column values."""
    return {
        "data": {
            "change_multiple_column_values": {
                "id": "111",
                "name": "Implement auth service",
                "column_values": [
                    {"id": "status", "type": "status", "text": "Done", "value": '{"index":5}'},
                ],
            }
        }
    }


# ---------------------------------------------------------------------------
# Agent YAML fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_agent_yaml(tmp_path: Path) -> Path:
    """Create a minimal valid agent YAML for testing."""
    content = """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: test-agent
  display_name: "Test Agent"
  description: "A test agent for unit tests"
  version: "1.0.0"
  tags: ["test"]

a2a:
  port: 19999
  skills:
    - id: do_test
      name: "Do Test"
      description: "Performs a test action"
  capabilities:
    streaming: false

llm:
  model: "anthropic/claude-sonnet-4-20250514"
  temperature: 0.1
  max_tokens: 1024

tools:
  mcp_servers: []

monday:
  board_id: "123456789"
  default_group: "To Do"

prompt:
  system: "You are a test agent."
"""
    yaml_file = tmp_path / "test-agent.yaml"
    yaml_file.write_text(content)
    return yaml_file


@pytest.fixture()
def sample_agent_yaml_with_env(tmp_path: Path) -> Path:
    """Agent YAML with environment variable placeholders."""
    content = """\
apiVersion: mfa/v1
kind: Agent
metadata:
  name: env-agent
  display_name: "Env Agent"
  description: "Agent with env var expansion"
  version: "1.0.0"

a2a:
  port: 19998

llm:
  model: "anthropic/claude-sonnet-4-20250514"

monday:
  board_id: "${MONDAY_BOARD_ID}"
  default_group: "To Do"

prompt:
  system: "Board ID is ${MONDAY_BOARD_ID}."
"""
    yaml_file = tmp_path / "env-agent.yaml"
    yaml_file.write_text(content)
    return yaml_file


# ---------------------------------------------------------------------------
# A2A message fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def a2a_send_request() -> dict[str, Any]:
    """A well-formed A2A message/send JSON-RPC request."""
    return {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "Build an authentication system"}],
                "messageId": "msg-test-1",
            }
        },
    }


@pytest.fixture()
def a2a_task_response() -> dict[str, Any]:
    """A well-formed A2A task response."""
    return {
        "jsonrpc": "2.0",
        "id": "test-1",
        "result": {
            "id": "task-1",
            "contextId": "ctx-test-1",
            "status": {
                "state": "completed",
                "message": {
                    "role": "agent",
                    "parts": [
                        {
                            "kind": "text",
                            "text": "I've created 3 tasks on the Monday.com board for the auth system.",
                        }
                    ],
                },
            },
        },
    }
