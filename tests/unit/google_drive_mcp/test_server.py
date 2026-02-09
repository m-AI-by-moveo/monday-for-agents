"""Tests for Google Drive MCP server tool registration."""

from __future__ import annotations

import pytest

from google_drive_mcp.server import mcp


@pytest.mark.unit
def test_server_has_expected_tools():
    """Verify the MCP server registers all expected tool names."""
    tool_names = [t.name for t in mcp._tool_manager.list_tools()]
    assert "list_drive_files" in tool_names
    assert "search_drive_files" in tool_names
    assert "read_drive_file" in tool_names
    assert "create_drive_file" in tool_names
    assert "update_drive_file" in tool_names
    assert "delete_drive_file" in tool_names


@pytest.mark.unit
def test_server_name():
    assert mcp.name == "google-drive"
