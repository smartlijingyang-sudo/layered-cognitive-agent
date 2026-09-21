"""Streamable HTTP / SSE MCP Transport implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import structlog

from lca.contracts.models.mcp.types import MCPServerConfig
from lca.contracts.protocols.mcp.ports import MCPTransportPort

_log = structlog.get_logger(__name__)


class StreamableHttpMCPTransport(MCPTransportPort):
    """MCP Streamable HTTP / SSE Transport using httpx."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._is_connected = False
        self._last_received_msg: dict[str, Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_connected(self) -> bool:
        if not self._is_connected or self._client is None or self._client.is_closed:
            return False
        try:
            curr_loop = asyncio.get_running_loop()
            if self._loop is not None and self._loop is not curr_loop:
                return False
        except RuntimeError:
            pass
        return True

    async def connect(self) -> None:
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._client is not None and curr_loop is not None and self._loop is not curr_loop:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
            self._is_connected = False

        if self.is_connected:
            return

        timeout = httpx.Timeout(
            connect=10.0,
            read=float(self._config.tool_timeout_ms) / 1000.0,
            write=10.0,
            pool=10.0,
        )
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            **self._config.headers,
        }
        self._client = httpx.AsyncClient(headers=headers, timeout=timeout)
        self._loop = curr_loop
        self._is_connected = True

    async def send_message(self, message: dict[str, Any]) -> None:
        if not self.is_connected or self._client is None:
            await self.connect()
        assert self._client is not None

        url = self._config.url
        if not url:
            raise ValueError(f"HTTP MCP server '{self._config.name}' must specify 'url'")

        try:
            resp = await self._client.post(url, json=message)
            resp.raise_for_status()

            if resp.status_code == 204 or not resp.text.strip():
                self._last_received_msg = None
                return

            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                # Parse SSE lines: find data: {...}
                for line in resp.text.splitlines():
                    line = line.strip()
                    if line.startswith("data:"):
                        raw_data = line[len("data:") :].strip()
                        if raw_data:
                            self._last_received_msg = json.loads(raw_data)
                            break
            else:
                self._last_received_msg = resp.json()

        except Exception as e:
            _log.error("mcp_http_send_failed", server=self._config.name, error=str(e))
            self._last_received_msg = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32000, "message": str(e)},
            }

    async def receive_message(self, timeout_s: float | None = None) -> dict[str, Any]:
        if self._last_received_msg is not None:
            msg = self._last_received_msg
            self._last_received_msg = None
            return msg
        raise EOFError(f"No pending response for MCP server '{self._config.name}'")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._is_connected = False
        self._last_received_msg = None
