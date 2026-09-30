"""MCPHub — Aggregate Root for managing multiple MCP servers and tool namespace routing."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from lca.contracts.models.mcp.types import (
    MCPServerConfig,
    MCPServerStatus,
    MCPTool,
    MCPToolResult,
)
from lca.contracts.protocols.mcp.ports import MCPManagerPort
from lca.infrastructure.mcp.client import MCPClient
from lca.infrastructure.mcp.config import load_mcp_servers
from lca.infrastructure.mcp.routing import build_tool_routing_table

_log = structlog.get_logger(__name__)


class MCPHub(MCPManagerPort):
    """Orchestrates multiple MCP server connections and tools discovery."""

    def __init__(self, configs: dict[str, MCPServerConfig] | None = None) -> None:
        self._configs = configs if configs is not None else load_mcp_servers()
        self._clients: dict[str, MCPClient] = {}
        for name, cfg in self._configs.items():
            self._clients[name] = MCPClient(cfg)

        # Cached index of tools
        self._tool_cache: dict[str, tuple[str, MCPTool]] = {}  # lookup_key -> (server_name, tool)

    @property
    def servers(self) -> dict[str, MCPClient]:
        return dict(self._clients)

    async def initialize(self) -> None:
        """Start all configured servers concurrently."""
        if not self._clients:
            return

        async def _safe_start(server_name: str, client: MCPClient) -> None:
            try:
                await client.start()
            except Exception as exc:
                _log.warning("mcp_server_init_failed", server=server_name, error=str(exc))

        tasks = [_safe_start(name, client) for name, client in self._clients.items()]
        await asyncio.gather(*tasks)

        # Build tool index
        self._rebuild_tool_index()

    def _rebuild_tool_index(self) -> None:
        healthy_tools = [
            (server_name, tool)
            for server_name, client in self._clients.items()
            if client.status == MCPServerStatus.HEALTHY
            for tool in client._tools
        ]
        self._tool_cache, collisions = build_tool_routing_table(healthy_tools)
        for raw_name, servers in collisions.items():
            _log.debug("mcp_tool_name_collision", tool=raw_name, servers=servers)

    def get_all_tools(self) -> list[MCPTool]:
        """Return list of all discovered tools across healthy servers."""
        tools: list[MCPTool] = []
        for client in self._clients.values():
            if client.status == MCPServerStatus.HEALTHY:
                tools.extend(client._tools)
        return tools

    def get_tool(self, qualified_or_raw_name: str) -> MCPTool | None:
        entry = self._tool_cache.get(qualified_or_raw_name)
        return entry[1] if entry else None

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> MCPToolResult:
        """Route tool execution to the hosting MCP server."""
        entry = self._tool_cache.get(tool_name)
        if entry is None:
            return MCPToolResult(
                is_error=True,
                content=[],
                structured_content=None,
                latency_ms=0,
            )

        server_name, tool = entry
        client = self._clients.get(server_name)
        if client is None:
            raise RuntimeError(f"Server '{server_name}' missing from active clients")

        # Call with original server tool name
        return await client.call_tool(tool.name, arguments, timeout_ms=timeout_ms)

    async def close(self) -> None:
        """Gracefully disconnect all active MCP servers."""
        tasks = [client.close() for client in self._clients.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tool_cache.clear()

    def close_sync(self) -> None:
        """Synchronously disconnect all active MCP servers without event loop."""
        for client in self._clients.values():
            if hasattr(client, "close_sync"):
                client.close_sync()
        self._tool_cache.clear()

    def doctor(self) -> dict[str, Any]:
        """Health diagnostics status report."""
        report: dict[str, Any] = {
            "total_servers": len(self._clients),
            "healthy_servers": 0,
            "failed_servers": 0,
            "total_tools": len(self.get_all_tools()),
            "servers": {},
        }
        for name, client in self._clients.items():
            is_healthy = client.status == MCPServerStatus.HEALTHY
            if is_healthy:
                report["healthy_servers"] += 1
            else:
                report["failed_servers"] += 1

            report["servers"][name] = {
                "status": client.status.value,
                "transport": client._config.transport.value,
                "tools": [t.name for t in client._tools],
                "last_error": client.last_error,
            }
        return report
