"""Model Context Protocol (MCP) domain models, value objects, and enums."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class MCPTransportType(StrEnum):
    """Supported MCP transport wire types."""

    STDIO = "stdio"
    HTTP = "http"
    STREAMABLE_HTTP = "streamable-http"
    SSE = "sse"


class MCPServerStatus(StrEnum):
    """Lifecycle status of a registered MCP server connection."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class MCPReconnectPolicy(BaseModel):
    """Exponential backoff reconnect policy (inspired by DeepSeek Harness)."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    initial_delay_ms: int = Field(default=500, ge=100)
    max_delay_ms: int = Field(default=30_000, ge=1_000)
    max_attempts: int = Field(default=10, ge=1)


class MCPServerConfig(BaseModel):
    """Configuration specification for an external MCP server."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(description="Namespace identifier, e.g. 'exa', 'searxng', 'github'")
    transport: MCPTransportType = Field(default=MCPTransportType.STDIO)

    # stdio configuration
    command: str | None = Field(default=None, description="Executable command for stdio transport")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    cwd: str | None = Field(default=None, description="Working directory")

    # http / streamable-http configuration
    url: str | None = Field(default=None, description="Remote MCP endpoint URL")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers, e.g. Authorization or x-api-key")

    # Timeouts & policies
    startup_timeout_ms: int = Field(default=30_000, ge=1_000, description="Initialization timeout")
    tool_timeout_ms: int = Field(default=60_000, ge=1_000, description="Per-tool call timeout")
    enabled: bool = Field(default=True, description="Whether this server is active")
    reconnect: MCPReconnectPolicy = Field(default_factory=MCPReconnectPolicy)


class MCPTool(BaseModel):
    """Normalized MCP tool definition exposed by remote server."""

    model_config = ConfigDict(extra="ignore")

    server_name: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None

    @property
    def qualified_name(self) -> str:
        """Stable namespaced name: mcp__{server_name}__{tool_name}."""
        return f"mcp__{self.server_name}__{self.name}"


class MCPToolCall(BaseModel):
    """Invocation request for an MCP tool."""

    model_config = ConfigDict(extra="ignore")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = ""


class MCPToolContentChunk(BaseModel):
    """A single piece of tool output (text, image, resource)."""

    model_config = ConfigDict(extra="ignore")

    type: str = "text"  # "text" | "image" | "resource"
    text: str | None = None
    data: str | None = None  # Base64 data for images
    mime_type: str | None = None


class MCPToolResult(BaseModel):
    """Result of executing an MCP tool."""

    model_config = ConfigDict(extra="ignore")

    is_error: bool = False
    content: list[MCPToolContentChunk] = Field(default_factory=list)
    structured_content: Any = None
    latency_ms: int = 0

    @property
    def text_content(self) -> str:
        """Extract merged textual output."""
        chunks = [c.text for c in self.content if c.text is not None]
        return "\n".join(chunks) if chunks else ""
