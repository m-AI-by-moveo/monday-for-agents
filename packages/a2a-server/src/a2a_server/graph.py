"""Build a LangGraph ReAct agent from an AgentDefinition."""

from __future__ import annotations

import logging
import shutil
import sys
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent

from a2a_server.models import AgentDefinition, MCPServerRef

logger = logging.getLogger(__name__)


def _parse_llm(model_string: str, temperature: float, max_tokens: int) -> Any:
    """Instantiate the correct LangChain chat model from a provider/model string.

    Currently only ``anthropic/`` prefixed models are supported.

    Args:
        model_string: Model identifier such as ``"anthropic/claude-sonnet-4-20250514"``.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in a single completion.

    Returns:
        A LangChain chat model instance.

    Raises:
        ValueError: If the provider prefix is not recognised.
    """
    if model_string.startswith("anthropic/"):
        model_name = model_string.removeprefix("anthropic/")
        logger.info("Using ChatAnthropic model=%s", model_name)
        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(
        f"Unsupported model provider in '{model_string}'. "
        "Expected a prefix like 'anthropic/'."
    )


def _resolve_mcp_server_command(ref: MCPServerRef) -> dict[str, Any]:
    """Resolve an MCPServerRef to MultiServerMCPClient connection parameters.

    For ``builtin:monday-mcp`` the function looks up the ``monday-mcp``
    console-script installed by the sibling package.  Falls back to
    running the module via ``python -m monday_mcp.server``.

    Returns:
        A dict suitable for passing as a server entry to
        :class:`MultiServerMCPClient`.
    """
    if ref.source.startswith("builtin:"):
        builtin_name = ref.source.removeprefix("builtin:")
        # Attempt to find the installed console script
        script_path = shutil.which(builtin_name)
        if script_path:
            command = script_path
            args: list[str] = []
        else:
            # Fallback: run as a Python module
            module_name = builtin_name.replace("-", "_") + ".server"
            command = sys.executable
            args = ["-m", module_name]

        logger.info(
            "Resolved builtin MCP server '%s' -> command=%s args=%s",
            ref.name,
            command,
            args,
        )
        return {
            "command": command,
            "args": args,
            "transport": "stdio",
        }

    raise ValueError(
        f"Unsupported MCP server source: '{ref.source}'. "
        "Only 'builtin:<name>' is currently supported."
    )


async def build_graph(
    agent_def: AgentDefinition,
    extra_tools: list[Any] | None = None,
) -> CompiledGraph:
    """Build and compile a LangGraph ReAct agent from *agent_def*.

    Args:
        agent_def: The parsed agent definition.
        extra_tools: Additional LangChain-compatible tools (e.g.
            ``send_message_to_agent``) to attach to the agent.

    Returns:
        A compiled LangGraph ready to be invoked.
    """
    # --- 1. LLM ---
    llm = _parse_llm(
        agent_def.llm.model,
        agent_def.llm.temperature,
        agent_def.llm.max_tokens,
    )

    # --- 2. MCP tools ---
    mcp_tools: list[Any] = []
    mcp_server_params: dict[str, dict[str, Any]] = {}

    for ref in agent_def.tools.mcp_servers:
        mcp_server_params[ref.name] = _resolve_mcp_server_command(ref)

    if mcp_server_params:
        logger.info("Connecting to MCP servers: %s", list(mcp_server_params.keys()))
        client = MultiServerMCPClient(mcp_server_params)
        mcp_tools = await client.get_tools()
        logger.info("Loaded %d tool(s) from MCP servers", len(mcp_tools))

    # --- 3. Combine tools ---
    all_tools: list[Any] = list(mcp_tools)
    if extra_tools:
        all_tools.extend(extra_tools)

    logger.info("Agent '%s' has %d total tool(s)", agent_def.metadata.name, len(all_tools))

    # --- 4. Build ReAct agent ---
    system_message = agent_def.prompt.system or None
    checkpointer = MemorySaver()

    graph = create_react_agent(
        model=llm,
        tools=all_tools,
        prompt=system_message,
        checkpointer=checkpointer,
    )

    logger.info("Graph compiled for agent '%s'", agent_def.metadata.name)
    return graph
