"""MCP Transports factory and registry."""

from __future__ import annotations

from lca.contracts.models.mcp.types import MCPServerConfig, MCPTransportType
from lca.contracts.protocols.mcp.ports import MCPTransportPort
from lca.infrastructure.mcp.transports.http import StreamableHttpMCPTransport
from lca.infrastructure.mcp.transports.stdio import StdioMCPTransport


def create_mcp_transport(config: MCPServerConfig) -> MCPTransportPort:
    """Instantiate appropriate transport port according to server config."""
    if config.transport == MCPTransportType.STDIO:
        return StdioMCPTransport(config)
    elif config.transport in (
        MCPTransportType.HTTP,
        MCPTransportType.STREAMABLE_HTTP,
        MCPTransportType.SSE,
    ):
        return StreamableHttpMCPTransport(config)
    raise ValueError(f"Unsupported MCP transport type: {config.transport}")


__all__ = [
    "StdioMCPTransport",
    "StreamableHttpMCPTransport",
    "create_mcp_transport",
]
