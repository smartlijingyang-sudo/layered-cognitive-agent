"""CDP Screencast frame relay and client connection manager (INV-BROWSER-04)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from lca.contracts.models.browser.stream import BrowserSessionStatus

logger = logging.getLogger(__name__)


class CDPScreencastRelay:
    """Chromium 原生 CDP Screencast 帧中继器与 WebSocket 客户端管理器。

    不变量：
    - INV-BROWSER-04: 二进制数据首字节固定为 0x01，表示 JPEG/WebP 图像帧。
    - 内置 _in_flight 计数器防背压溢出；未确认帧达到 max_in_flight 时主动节流丢帧。
    """

    FRAME_TYPE_BINARY_JPEG: int = 0x01

    def __init__(
        self,
        session_id: str,
        max_in_flight: int = 3,
    ) -> None:
        self.session_id = session_id
        self.max_in_flight = max_in_flight
        self._clients: set[Any] = set()
        self._in_flight: int = 0
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        """已连接的 WebSocket 客户端总数。"""
        return len(self._clients)

    def register_client(self, ws: Any) -> None:
        """注册新的前端 WebSocket 客户端。"""
        self._clients.add(ws)
        logger.debug("[CDPScreencastRelay] Registered client for session %s (total: %d)", self.session_id, len(self._clients))

    def unregister_client(self, ws: Any) -> None:
        """注销前端 WebSocket 客户端。"""
        self._clients.discard(ws)
        logger.debug("[CDPScreencastRelay] Unregistered client for session %s (remaining: %d)", self.session_id, len(self._clients))

    async def emit_frame(
        self,
        data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """下行广播二进制 Screencast 帧。

        若当前未确认帧超过 max_in_flight 阈值，则主动丢弃当前帧以提供背压保护。
        """
        if not self._clients:
            return False

        async with self._lock:
            if self._in_flight >= self.max_in_flight:
                logger.debug(
                    "[CDPScreencastRelay] Throttle drop frame for session %s (in_flight=%d >= max=%d)",
                    self.session_id,
                    self._in_flight,
                    self.max_in_flight,
                )
                return False

            self._in_flight += 1

        payload = bytes([self.FRAME_TYPE_BINARY_JPEG]) + data
        dead_clients = []

        for ws in list(self._clients):
            try:
                await ws.send_bytes(payload)
            except Exception as e:
                logger.warning("[CDPScreencastRelay] Failed to send frame to client: %s", e)
                dead_clients.append(ws)

        for ws in dead_clients:
            self.unregister_client(ws)

        return True

    def handle_ack(self) -> None:
        """处理来自前端的帧渲染确认（ACK）。"""
        self._in_flight = max(0, self._in_flight - 1)

    async def emit_status(self, status: BrowserSessionStatus | str) -> None:
        """向所有客户端广播状态变更通知。"""
        if not self._clients:
            return
        status_val = status.value if isinstance(status, BrowserSessionStatus) else str(status)
        payload = {
            "type": "status",
            "session_id": self.session_id,
            "status": status_val,
        }
        await self._broadcast_json(payload)

    async def emit_metadata(self, metadata: dict[str, Any]) -> None:
        """向所有客户端广播网页元数据变更（URL、Title、视口尺寸等）。"""
        if not self._clients:
            return
        payload = {
            "type": "metadata",
            "session_id": self.session_id,
            **metadata,
        }
        await self._broadcast_json(payload)

    async def _broadcast_json(self, payload: dict[str, Any]) -> None:
        dead_clients = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.warning("[CDPScreencastRelay] Failed to send json to client: %s", e)
                dead_clients.append(ws)

        for ws in dead_clients:
            self.unregister_client(ws)

    async def close(self) -> None:
        """优雅关闭中继器并断开所有客户端。"""
        clients = list(self._clients)
        self._clients.clear()
        self._in_flight = 0
        for ws in clients:
            with contextlib.suppress(Exception):
                await ws.close()


__all__ = ["CDPScreencastRelay"]
