"""MCPClient — supervisor and JSON-RPC 2.0 client for a single MCP server."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from lca.contracts.models.mcp.types import (
    MCPServerConfig,
    MCPServerStatus,
    MCPTool,
    MCPToolContentChunk,
    MCPToolResult,
)
from lca.contracts.protocols.mcp.ports import MCPClientPort
from lca.infrastructure.mcp.transports import create_mcp_transport

_log = structlog.get_logger(__name__)


class MCPClient(MCPClientPort):
    """Supervised client for a single MCP server."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._transport = create_mcp_transport(config)
        self._status = MCPServerStatus.DISCONNECTED
        self._req_counter = 0
        self._tools: list[MCPTool] = []
        self._lock = asyncio.Lock()
        self._last_error: str = ""

    @property
    def server_name(self) -> str:
        return self._config.name

    @property
    def status(self) -> MCPServerStatus:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    def _next_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    async def start(self) -> None:
        """Establish connection, perform protocol handshake, and discover tools."""
        async with self._lock:
            self._status = MCPServerStatus.CONNECTING
            try:
                await self._transport.connect()

                # Step 1: initialize handshake
                init_id = self._next_id()
                init_msg = {
                    "jsonrpc": "2.0",
                    "id": init_id,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "layered-cognitive-agent", "version": "0.1.0"},
                    },
                }
                await self._transport.send_message(init_msg)
                init_resp = await self._transport.receive_message(
                    timeout_s=float(self._config.startup_timeout_ms) / 1000.0
                )

                if "error" in init_resp:
                    raise RuntimeError(f"MCP init error: {init_resp['error']}")

                # Step 2: notifications/initialized
                await self._transport.send_message(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"}
                )

                # Step 3: tools/list initial discovery
                self._tools = await self._fetch_tools_internal()
                self._status = MCPServerStatus.HEALTHY
                _log.info(
                    "mcp_server_connected",
                    server=self.server_name,
                    tools_count=len(self._tools),
                )
            except Exception as e:
                self._status = MCPServerStatus.FAILED
                self._last_error = str(e)
                _log.warning("mcp_server_start_failed", server=self.server_name, error=str(e))
                # Close transport on failure
                await self._transport.close()
                raise

    async def _fetch_tools_internal(self) -> list[MCPTool]:
        list_id = self._next_id()
        await self._transport.send_message(
            {"jsonrpc": "2.0", "id": list_id, "method": "tools/list", "params": {}}
        )
        resp = await self._transport.receive_message(
            timeout_s=float(self._config.startup_timeout_ms) / 1000.0
        )

        if "error" in resp:
            raise RuntimeError(f"tools/list error: {resp['error']}")

        result = resp.get("result", {})
        raw_tools = result.get("tools", [])

        tools: list[MCPTool] = []
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            tools.append(
                MCPTool(
                    server_name=self.server_name,
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    input_schema=item.get("inputSchema", {}),
                    output_schema=item.get("outputSchema"),
                )
            )
        return tools

    async def list_tools(self) -> list[MCPTool]:
        if self._status != MCPServerStatus.HEALTHY:
            return []
        return list(self._tools)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> MCPToolResult:
        """Call an MCP tool with timeout and latency recording."""
        start = time.monotonic()
        call_timeout = float(timeout_ms or self._config.tool_timeout_ms) / 1000.0

        if not self._transport.is_connected:
            try:
                await self.start()
            except Exception as exc:
                return MCPToolResult(
                    is_error=True,
                    content=[
                        MCPToolContentChunk(
                            type="text",
                            text=f"MCP server '{self.server_name}' is disconnected: {exc}",
                        )
                    ],
                    latency_ms=0,
                )

        call_id = self._next_id()
        msg = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        try:
            async with self._lock:
                await self._transport.send_message(msg)
                resp = await self._transport.receive_message(timeout_s=call_timeout)

            latency_ms = int((time.monotonic() - start) * 1000)

            if "error" in resp:
                err = resp["error"]
                err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return MCPToolResult(
                    is_error=True,
                    content=[MCPToolContentChunk(type="text", text=f"Tool error: {err_msg}")],
                    latency_ms=latency_ms,
                )

            res = resp.get("result", {})
            is_error = bool(res.get("isError", False))

            chunks: list[MCPToolContentChunk] = []
            for item in res.get("content", []):
                if isinstance(item, dict):
                    chunks.append(
                        MCPToolContentChunk(
                            type=item.get("type", "text"),
                            text=item.get("text"),
                            data=item.get("data"),
                            mime_type=item.get("mimeType"),
                        )
                    )

            return MCPToolResult(
                is_error=is_error,
                content=chunks,
                structured_content=res.get("structuredContent"),
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            _log.error("mcp_call_tool_failed", server=self.server_name, tool=tool_name, error=str(e))
            return MCPToolResult(
                is_error=True,
                content=[MCPToolContentChunk(type="text", text=f"Call failed: {str(e)}")],
                latency_ms=latency_ms,
            )

    async def close(self) -> None:
        async with self._lock:
            await self._transport.close()
            self._status = MCPServerStatus.DISCONNECTED
            self._tools.clear()
