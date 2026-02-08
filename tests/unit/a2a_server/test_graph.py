"""Unit tests for a2a_server.graph — LangGraph ReAct agent construction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_server.graph import _parse_llm, _resolve_mcp_server_command, build_graph
from a2a_server.models import (
    A2AConfig,
    AgentDefinition,
    AgentMetadata,
    LLMConfig,
    MCPServerRef,
    PromptConfig,
    ToolsConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent_def(
    *,
    mcp_servers: list[MCPServerRef] | None = None,
    model: str = "anthropic/claude-sonnet-4-20250514",
    system_prompt: str = "You are a test agent.",
) -> AgentDefinition:
    """Build a minimal AgentDefinition for testing."""
    return AgentDefinition(
        metadata=AgentMetadata(name="graph-test-agent"),
        a2a=A2AConfig(port=19999),
        llm=LLMConfig(model=model, temperature=0.1, max_tokens=1024),
        tools=ToolsConfig(mcp_servers=mcp_servers or []),
        prompt=PromptConfig(system=system_prompt),
    )


# ---------------------------------------------------------------------------
# _parse_llm
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseLlm:
    """Tests for the _parse_llm() helper."""

    @patch("a2a_server.graph.ChatAnthropic")
    def test_anthropic_prefix_creates_chat_anthropic(
        self, mock_chat_anthropic: MagicMock
    ) -> None:
        """A model string with 'anthropic/' prefix instantiates ChatAnthropic."""
        mock_chat_anthropic.return_value = MagicMock(name="FakeLLM")

        result = _parse_llm("anthropic/claude-sonnet-4-20250514", temperature=0.2, max_tokens=512)

        mock_chat_anthropic.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            temperature=0.2,
            max_tokens=512,
        )
        assert result == mock_chat_anthropic.return_value

    @patch("a2a_server.graph.ChatAnthropic")
    def test_anthropic_prefix_strips_correctly(
        self, mock_chat_anthropic: MagicMock
    ) -> None:
        """The 'anthropic/' prefix is stripped to get the model name."""
        _parse_llm("anthropic/my-custom-model", temperature=0.0, max_tokens=100)

        call_kwargs = mock_chat_anthropic.call_args[1]
        assert call_kwargs["model"] == "my-custom-model"

    def test_raises_for_unknown_provider(self) -> None:
        """_parse_llm() raises ValueError for unrecognised provider prefixes."""
        with pytest.raises(ValueError, match="Unsupported model provider"):
            _parse_llm("openai/gpt-4", temperature=0.5, max_tokens=1024)

    def test_raises_for_no_prefix(self) -> None:
        """_parse_llm() raises ValueError when no provider prefix is present."""
        with pytest.raises(ValueError, match="Unsupported model provider"):
            _parse_llm("claude-sonnet-4-20250514", temperature=0.5, max_tokens=1024)


# ---------------------------------------------------------------------------
# _resolve_mcp_server_command
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveMcpServerCommand:
    """Tests for _resolve_mcp_server_command()."""

    @patch("a2a_server.graph.shutil.which", return_value="/usr/local/bin/monday-mcp")
    def test_builtin_monday_mcp_with_script_found(self, mock_which: MagicMock) -> None:
        """When the console script is found, its path is used as the command."""
        ref = MCPServerRef(name="monday", source="builtin:monday-mcp")
        result = _resolve_mcp_server_command(ref)

        assert result["command"] == "/usr/local/bin/monday-mcp"
        assert result["args"] == []
        assert result["transport"] == "stdio"
        mock_which.assert_called_once_with("monday-mcp")

    @patch("a2a_server.graph.shutil.which", return_value=None)
    @patch("a2a_server.graph.sys")
    def test_builtin_monday_mcp_with_fallback(
        self, mock_sys: MagicMock, mock_which: MagicMock
    ) -> None:
        """When the console script is not found, falls back to python -m."""
        mock_sys.executable = "/usr/bin/python3"
        ref = MCPServerRef(name="monday", source="builtin:monday-mcp")
        result = _resolve_mcp_server_command(ref)

        assert result["command"] == "/usr/bin/python3"
        assert result["args"] == ["-m", "monday_mcp.server"]
        assert result["transport"] == "stdio"

    def test_raises_for_unsupported_source(self) -> None:
        """_resolve_mcp_server_command() raises for non-builtin sources."""
        ref = MCPServerRef(name="custom", source="https://example.com/mcp")
        with pytest.raises(ValueError, match="Unsupported MCP server source"):
            _resolve_mcp_server_command(ref)

    @patch("a2a_server.graph.shutil.which", return_value="/usr/bin/other-tool")
    def test_builtin_generic_name(self, mock_which: MagicMock) -> None:
        """builtin: prefix works with arbitrary names, not only monday-mcp."""
        ref = MCPServerRef(name="other", source="builtin:other-tool")
        result = _resolve_mcp_server_command(ref)

        assert result["command"] == "/usr/bin/other-tool"
        mock_which.assert_called_once_with("other-tool")


# ---------------------------------------------------------------------------
# build_graph
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildGraph:
    """Tests for the build_graph() async function."""

    @patch("a2a_server.graph.create_react_agent")
    @patch("a2a_server.graph.MemorySaver")
    @patch("a2a_server.graph.ChatAnthropic")
    async def test_creates_compiled_graph_no_mcp(
        self,
        mock_anthropic: MagicMock,
        mock_saver: MagicMock,
        mock_create_react: MagicMock,
    ) -> None:
        """build_graph() creates a compiled graph when there are no MCP servers."""
        mock_llm = MagicMock(name="FakeLLM")
        mock_anthropic.return_value = mock_llm
        mock_graph = MagicMock(name="FakeCompiledGraph")
        mock_create_react.return_value = mock_graph

        agent_def = _make_agent_def()
        result = await build_graph(agent_def)

        mock_create_react.assert_called_once()
        call_kwargs = mock_create_react.call_args[1]
        assert call_kwargs["model"] is mock_llm
        assert call_kwargs["tools"] == []
        assert call_kwargs["prompt"] == "You are a test agent."
        assert result is mock_graph

    @patch("a2a_server.graph.create_react_agent")
    @patch("a2a_server.graph.MemorySaver")
    @patch("a2a_server.graph.ChatAnthropic")
    async def test_includes_extra_tools(
        self,
        mock_anthropic: MagicMock,
        mock_saver: MagicMock,
        mock_create_react: MagicMock,
    ) -> None:
        """build_graph() appends extra_tools to the tool list."""
        mock_anthropic.return_value = MagicMock()
        mock_create_react.return_value = MagicMock()

        fake_tool = MagicMock(name="FakeExtraTool")
        agent_def = _make_agent_def()
        await build_graph(agent_def, extra_tools=[fake_tool])

        call_kwargs = mock_create_react.call_args[1]
        assert fake_tool in call_kwargs["tools"]

    @patch("a2a_server.graph.create_react_agent")
    @patch("a2a_server.graph.MemorySaver")
    @patch("a2a_server.graph.MultiServerMCPClient")
    @patch("a2a_server.graph.ChatAnthropic")
    async def test_connects_mcp_servers(
        self,
        mock_anthropic: MagicMock,
        mock_mcp_client_cls: MagicMock,
        mock_saver: MagicMock,
        mock_create_react: MagicMock,
    ) -> None:
        """build_graph() connects to MCP servers and loads their tools."""
        mock_anthropic.return_value = MagicMock()
        mock_create_react.return_value = MagicMock()

        mcp_tool_1 = MagicMock(name="MCPTool1")
        mcp_tool_2 = MagicMock(name="MCPTool2")
        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[mcp_tool_1, mcp_tool_2])
        mock_mcp_client_cls.return_value = mock_client

        agent_def = _make_agent_def(
            mcp_servers=[MCPServerRef(name="monday", source="builtin:monday-mcp")]
        )

        with patch("a2a_server.graph.shutil.which", return_value="/usr/bin/monday-mcp"):
            await build_graph(agent_def)

        mock_mcp_client_cls.assert_called_once()
        call_kwargs = mock_create_react.call_args[1]
        assert mcp_tool_1 in call_kwargs["tools"]
        assert mcp_tool_2 in call_kwargs["tools"]

    @patch("a2a_server.graph.create_react_agent")
    @patch("a2a_server.graph.MemorySaver")
    @patch("a2a_server.graph.ChatAnthropic")
    async def test_system_prompt_none_when_empty(
        self,
        mock_anthropic: MagicMock,
        mock_saver: MagicMock,
        mock_create_react: MagicMock,
    ) -> None:
        """build_graph() passes prompt=None when system prompt is empty."""
        mock_anthropic.return_value = MagicMock()
        mock_create_react.return_value = MagicMock()

        agent_def = _make_agent_def(system_prompt="")
        await build_graph(agent_def)

        call_kwargs = mock_create_react.call_args[1]
        assert call_kwargs["prompt"] is None

    @patch("a2a_server.graph.create_react_agent")
    @patch("a2a_server.graph.MemorySaver")
    @patch("a2a_server.graph.MultiServerMCPClient")
    @patch("a2a_server.graph.ChatAnthropic")
    async def test_mcp_tools_combined_with_extra_tools(
        self,
        mock_anthropic: MagicMock,
        mock_mcp_client_cls: MagicMock,
        mock_saver: MagicMock,
        mock_create_react: MagicMock,
    ) -> None:
        """MCP tools and extra_tools are combined into one list."""
        mock_anthropic.return_value = MagicMock()
        mock_create_react.return_value = MagicMock()

        mcp_tool = MagicMock(name="MCPTool")
        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[mcp_tool])
        mock_mcp_client_cls.return_value = mock_client

        extra = MagicMock(name="ExtraTool")
        agent_def = _make_agent_def(
            mcp_servers=[MCPServerRef(name="monday", source="builtin:monday-mcp")]
        )

        with patch("a2a_server.graph.shutil.which", return_value="/usr/bin/monday-mcp"):
            await build_graph(agent_def, extra_tools=[extra])

        call_kwargs = mock_create_react.call_args[1]
        assert mcp_tool in call_kwargs["tools"]
        assert extra in call_kwargs["tools"]
        assert len(call_kwargs["tools"]) == 2
