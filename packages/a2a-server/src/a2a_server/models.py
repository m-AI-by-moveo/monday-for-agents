"""Pydantic models for agent definition YAML schema."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentMetadata(BaseModel):
    """Metadata block identifying the agent."""

    name: str = Field(..., description="Unique agent identifier (e.g. 'product-owner')")
    display_name: str = Field("", description="Human-readable display name")
    description: str = Field("", description="Short description of the agent's purpose")
    version: str = Field("1.0.0", description="Semantic version of the agent definition")
    tags: list[str] = Field(default_factory=list, description="Categorisation tags")


class A2ASkill(BaseModel):
    """A single skill exposed by the agent over A2A."""

    id: str = Field(..., description="Unique skill identifier")
    name: str = Field("", description="Human-readable skill name")
    description: str = Field("", description="What this skill does")


class A2ACapabilities(BaseModel):
    """Capabilities advertised in the A2A Agent Card."""

    streaming: bool = Field(False, description="Whether the agent supports streaming responses")


class A2AConfig(BaseModel):
    """A2A protocol configuration."""

    port: int = Field(10000, description="Port the A2A server listens on")
    skills: list[A2ASkill] = Field(default_factory=list, description="Skills exposed over A2A")
    capabilities: A2ACapabilities = Field(
        default_factory=A2ACapabilities,
        description="Agent capabilities",
    )


class LLMConfig(BaseModel):
    """LLM provider and parameter configuration."""

    model: str = Field(
        "anthropic/claude-sonnet-4-20250514",
        description="Model identifier in provider/model format",
    )
    temperature: float = Field(0.3, description="Sampling temperature")
    max_tokens: int = Field(4096, description="Maximum tokens in a single response")


class MCPServerRef(BaseModel):
    """Reference to an MCP server the agent should connect to."""

    name: str = Field(..., description="Logical name for the MCP server")
    source: str = Field(
        ...,
        description="Source locator, e.g. 'builtin:monday-mcp' or a URL",
    )


class ToolsConfig(BaseModel):
    """External tool configuration."""

    mcp_servers: list[MCPServerRef] = Field(
        default_factory=list,
        description="MCP servers to connect to for tool access",
    )


class MondayConfig(BaseModel):
    """Monday.com-specific configuration."""

    board_id: str = Field("", description="Monday board ID (supports env-var expansion)")
    default_group: str = Field("To Do", description="Default group for new items")


class PromptConfig(BaseModel):
    """Prompt templates for the agent."""

    system: str = Field("", description="System prompt injected into every conversation")


class ClaudeCodeConfig(BaseModel):
    """Configuration for the Claude Code CLI executor."""

    allowed_tools: list[str] = Field(
        default_factory=list,
        description="--allowedTools restrictions (empty = allow all)",
    )
    timeout: int = Field(600, description="Subprocess timeout in seconds")
    add_dirs: list[str] = Field(
        default_factory=list,
        description="--add-dir paths for additional file access",
    )


class AgentDefinition(BaseModel):
    """Root model representing a complete agent YAML file."""

    apiVersion: str = Field("mfa/v1", description="Schema version")  # noqa: N815
    kind: str = Field("Agent", description="Resource kind")
    metadata: AgentMetadata
    a2a: A2AConfig = Field(default_factory=A2AConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    monday: MondayConfig = Field(default_factory=MondayConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    claude_code: ClaudeCodeConfig = Field(
        default_factory=ClaudeCodeConfig,
        description="Claude Code CLI executor configuration",
    )
