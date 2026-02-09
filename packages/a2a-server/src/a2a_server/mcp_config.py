"""Build MCP config JSON for the Claude Code CLI --mcp-config flag."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from typing import Any

from a2a_server.models import AgentDefinition, MCPServerRef

logger = logging.getLogger(__name__)


def _resolve_mcp_server_entry(ref: MCPServerRef) -> dict[str, Any]:
    """Resolve an MCPServerRef to an MCP config entry for Claude Code.

    For ``builtin:monday-mcp`` the function looks up the ``monday-mcp``
    console-script installed by the sibling package.  Falls back to
    running the module via ``python -m monday_mcp.server``.

    Returns:
        A dict with ``command``, ``args``, and ``env`` keys.
    """
    if ref.source.startswith("builtin:"):
        builtin_name = ref.source.removeprefix("builtin:")
        script_path = shutil.which(builtin_name)
        if script_path:
            command = script_path
            args: list[str] = []
        else:
            module_name = builtin_name.replace("-", "_") + ".server"
            command = sys.executable
            args = ["-m", module_name]

        env: dict[str, str] = {}

        # Monday.com env vars (for builtin:monday-mcp)
        monday_token = os.environ.get("MONDAY_API_TOKEN", "")
        if monday_token:
            env["MONDAY_API_TOKEN"] = monday_token
        monday_board = os.environ.get("MONDAY_BOARD_ID", "")
        if monday_board:
            env["MONDAY_BOARD_ID"] = monday_board

        # Google env vars (for builtin:google-calendar-mcp / builtin:google-drive-mcp)
        google_sa_key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_FILE", "")
        if google_sa_key:
            env["GOOGLE_SERVICE_ACCOUNT_KEY_FILE"] = google_sa_key

        logger.info(
            "Resolved MCP server '%s' -> command=%s args=%s",
            ref.name, command, args,
        )
        return {"command": command, "args": args, "env": env}

    raise ValueError(
        f"Unsupported MCP server source: '{ref.source}'. "
        "Only 'builtin:<name>' is currently supported."
    )


def build_mcp_config(
    agent_def: AgentDefinition,
    agent_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the ``--mcp-config`` JSON dict for a Claude Code invocation.

    Args:
        agent_def: The agent definition with MCP server references.
        agent_urls: Mapping of agent name to A2A URL for the bridge server.
            If provided, an ``a2a-bridge`` MCP server entry is added.

    Returns:
        A dict suitable for serialising as MCP config JSON.
    """
    servers: dict[str, Any] = {}

    # Add MCP servers from agent definition
    for ref in agent_def.tools.mcp_servers:
        servers[ref.name] = _resolve_mcp_server_entry(ref)

    # Add A2A bridge MCP server if agent URLs are provided
    if agent_urls:
        bridge_env: dict[str, str] = {
            "MFA_AGENT_REGISTRY": json.dumps(agent_urls),
        }
        api_key = os.environ.get("MFA_API_KEY", "")
        if api_key:
            bridge_env["MFA_API_KEY"] = api_key

        servers["a2a-bridge"] = {
            "command": sys.executable,
            "args": ["-m", "a2a_server.a2a_bridge_mcp"],
            "env": bridge_env,
        }

    logger.info(
        "Built MCP config for agent '%s' with servers: %s",
        agent_def.metadata.name, list(servers.keys()),
    )
    return {"mcpServers": servers}
