"""Model Context Protocol (MCP) Ports / Domain Interfaces."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.mcp.types import (
    MCPServerConfig,
    MCPServerStatus,
    MCPTool,
    MCPToolResult,
)


@runtime_checkable
class MCPTransportPort(Protocol):
    """Low-level JSON-RPC 2.0 transport connection."""

    async def connect(self) -> None:
        """Establish transport connection (process spawn or HTTP handshake)."""
        ...

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send a JSON-RPC 2.0 message."""
        ...

    async def receive_message(self, timeout_s: float | None = None) -> dict[str, Any]:
        """Receive the next JSON-RPC 2.0 message."""
        ...

    async def close(self) -> None:
        """Close connection and clean up resources."""
        ...

    @property
    def is_connected(self) -> bool:
        """Connection liveness state."""
        ...


@runtime_checkable
class MCPClientPort(Protocol):
    """Client supervisor for a single MCP server."""

    @property
    def server_name(self) -> str:
        """Target server identifier."""
        ...

    @property
    def status(self) -> MCPServerStatus:
        """Current server status."""
        ...

    async def start(self) -> None:
        """Connect, initialize, and fetch initial tool generation."""
        ...

    async def list_tools(self) -> list[MCPTool]:
        """Query remote tools/list."""
        ...

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> MCPToolResult:
        """Invoke tools/call on the remote server."""
        ...

    async def close(self) -> None:
        """Gracefully disconnect."""
        ...


@runtime_checkable
class MCPManagerPort(Protocol):
    """Aggregate Root managing multiple MCP servers and tool namespace registry."""

    async def initialize(self) -> None:
        """Start and synchronize all configured MCP servers."""
        ...

    def get_all_tools(self) -> list[MCPTool]:
        """Return all active tools across all connected servers."""
        ...

    def get_tool(self, qualified_or_raw_name: str) -> MCPTool | None:
        """Look up tool by qualified name or raw name."""
        ...

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> MCPToolResult:
        """Route tool invocation to the correct MCP server."""
        ...

    async def close(self) -> None:
        """Tear down all server connections."""
        ...

    def doctor(self) -> dict[str, Any]:
        """Health check and diagnostics status."""
        ...
