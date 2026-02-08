"""Evaluation test fixtures.

Provides fixtures for LLM-based evaluation tests including a real
ChatAnthropic instance (skipped if ANTHROPIC_API_KEY is not set),
sample feature requests, expected task structures, and helpers
for extracting tool calls from LangGraph responses.
"""

from __future__ import annotations

import os
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# LLM fixture — real ChatAnthropic from environment
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_llm():
    """Create a real ChatAnthropic instance from the ANTHROPIC_API_KEY env var.

    Skips the test if the key is not set (prevents accidental failures
    in CI without secrets).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "test-key-do-not-use":
        pytest.skip("ANTHROPIC_API_KEY not set or is the test placeholder")

    # Import only when we actually have a key to avoid import errors
    # in environments without langchain_anthropic installed.
    ChatAnthropic = pytest.importorskip("langchain_anthropic").ChatAnthropic

    return ChatAnthropic(
        model="claude-sonnet-4-20250514",
        temperature=0.3,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Sample feature requests for testing
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_feature_requests() -> list[dict[str, str]]:
    """Return a set of sample feature requests with varying complexity.

    Each entry has a ``request`` (the user's message) and a ``category``
    describing the expected complexity.
    """
    return [
        {
            "request": "Build a user authentication system with email/password login, password reset, and session management.",
            "category": "complex",
        },
        {
            "request": "Add a dark mode toggle to the settings page.",
            "category": "simple",
        },
        {
            "request": "We need some kind of notification thing.",
            "category": "vague",
        },
        {
            "request": "Implement rate limiting for the API endpoints. We're getting too many requests from some clients and it's causing performance issues. Should support configurable limits per endpoint and per API key.",
            "category": "complex",
        },
        {
            "request": "Fix the bug where the dashboard crashes when there are no tasks.",
            "category": "bug",
        },
    ]


# ---------------------------------------------------------------------------
# Expected task structures
# ---------------------------------------------------------------------------


@pytest.fixture()
def expected_auth_tasks() -> list[dict[str, Any]]:
    """Expected task breakdown for the 'user auth' feature request.

    This represents the ideal output: what a well-functioning PO agent
    should produce when asked to build an auth system.
    """
    return [
        {
            "name_contains": ["auth", "login"],
            "priority": "High",
            "type": "Feature",
            "assignee": "developer",
        },
        {
            "name_contains": ["password", "reset"],
            "priority": "High",
            "type": "Feature",
            "assignee": "developer",
        },
        {
            "name_contains": ["session"],
            "priority": "Medium",
            "type": "Feature",
            "assignee": "developer",
        },
    ]


@pytest.fixture()
def expected_board_summary_structure() -> dict[str, Any]:
    """Expected structure for a board summary.

    Used to validate that the scrum master produces reports matching
    this schema.
    """
    return {
        "required_sections": [
            "Board Summary",
            "In Progress",
            "Blocked",
            "Action Items",
        ],
        "required_metrics": [
            "total",
            "To Do",
            "In Progress",
        ],
    }


# ---------------------------------------------------------------------------
# Tool call extraction helper
# ---------------------------------------------------------------------------


def extract_tool_calls(messages: list[Any]) -> list[dict[str, Any]]:
    """Extract tool call information from a list of LangGraph messages.

    Walks through the message list and collects every tool call found
    on AI messages.  Each returned dict has keys:
    - ``name``: The tool name.
    - ``args``: The tool arguments dict.
    - ``id``:   The tool call ID (if present).

    Args:
        messages: The ``messages`` list from a LangGraph invocation result.

    Returns:
        A list of tool-call dicts in invocation order.
    """
    calls: list[dict[str, Any]] = []
    for msg in messages:
        if getattr(msg, "type", None) != "ai":
            continue
        for tc in getattr(msg, "tool_calls", []) or []:
            calls.append(
                {
                    "name": tc.get("name", ""),
                    "args": tc.get("args", {}),
                    "id": tc.get("id", ""),
                }
            )
    return calls
