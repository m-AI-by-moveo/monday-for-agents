"""Tests for Google Calendar MCP server tool registration."""

from __future__ import annotations

import pytest

from google_calendar_mcp.server import mcp


@pytest.mark.unit
def test_server_has_expected_tools():
    """Verify the MCP server registers all expected tool names."""
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "list_calendar_events" in tool_names
    assert "create_calendar_event" in tool_names
    assert "update_calendar_event" in tool_names
    assert "delete_calendar_event" in tool_names


@pytest.mark.unit
def test_server_name():
    assert mcp.name == "google-calendar"
