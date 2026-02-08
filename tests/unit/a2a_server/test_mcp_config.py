"""Unit tests for a2a_server.mcp_config — MCP config builder."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from a2a_server.mcp_config import build_mcp_config, _resolve_mcp_server_entry
from a2a_server.models import (
    AgentDefinition,
    AgentMetadata,
    MCPServerRef,
    ToolsConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_def(
    name: str = "test-agent",
    mcp_servers: list[MCPServerRef] | None = None,
) -> AgentDefinition:
    """Build a minimal AgentDefinition for testing."""
    return AgentDefinition(
        metadata=AgentMetadata(name=name),
        tools=ToolsConfig(mcp_servers=mcp_servers or []),
    )


# ---------------------------------------------------------------------------
# _resolve_mcp_server_entry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveMcpServerEntry:
    """Tests for _resolve_mcp_server_entry()."""

    @patch("a2a_server.mcp_config.shutil.which", return_value="/usr/local/bin/monday-mcp")
    def test_builtin_uses_script_path(self, mock_which) -> None:
        ref = MCPServerRef(name="monday", source="builtin:monday-mcp")
        result = _resolve_mcp_server_entry(ref)

        assert result["command"] == "/usr/local/bin/monday-mcp"
        assert result["args"] == []
        mock_which.assert_called_once_with("monday-mcp")

    @patch("a2a_server.mcp_config.shutil.which", return_value=None)
    @patch("a2a_server.mcp_config.sys")
    def test_builtin_falls_back_to_module(self, mock_sys, mock_which) -> None:
        mock_sys.executable = "/usr/bin/python3"
        ref = MCPServerRef(name="monday", source="builtin:monday-mcp")
        result = _resolve_mcp_server_entry(ref)

        assert result["command"] == "/usr/bin/python3"
        assert result["args"] == ["-m", "monday_mcp.server"]

    def test_raises_for_unsupported_source(self) -> None:
        ref = MCPServerRef(name="custom", source="https://example.com")
        with pytest.raises(ValueError, match="Unsupported MCP server source"):
            _resolve_mcp_server_entry(ref)


# ---------------------------------------------------------------------------
# build_mcp_config
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildMcpConfig:
    """Tests for build_mcp_config()."""

    @patch("a2a_server.mcp_config.shutil.which", return_value="/usr/bin/monday-mcp")
    def test_includes_mcp_servers_from_definition(self, mock_which) -> None:
        agent_def = _make_agent_def(
            mcp_servers=[MCPServerRef(name="monday", source="builtin:monday-mcp")],
        )
        config = build_mcp_config(agent_def)

        assert "monday" in config["mcpServers"]
        assert config["mcpServers"]["monday"]["command"] == "/usr/bin/monday-mcp"

    def test_includes_a2a_bridge_when_urls_provided(self) -> None:
        agent_def = _make_agent_def()
        agent_urls = {"developer": "http://localhost:10002"}
        config = build_mcp_config(agent_def, agent_urls=agent_urls)

        assert "a2a-bridge" in config["mcpServers"]
        bridge = config["mcpServers"]["a2a-bridge"]
        assert bridge["args"] == ["-m", "a2a_server.a2a_bridge_mcp"]
        assert "MFA_AGENT_REGISTRY" in bridge["env"]

    def test_no_bridge_when_no_urls(self) -> None:
        agent_def = _make_agent_def()
        config = build_mcp_config(agent_def)

        assert "a2a-bridge" not in config["mcpServers"]

    def test_empty_mcp_servers(self) -> None:
        agent_def = _make_agent_def()
        config = build_mcp_config(agent_def)

        assert config == {"mcpServers": {}}
