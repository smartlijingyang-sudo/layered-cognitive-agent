"""Playwright & Chrome DevTools Protocol (CDP) Browser Driver implementation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
    BrowserSessionSummary,
)
from lca.contracts.protocols.browser import BrowserDriverPort
from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay

logger = logging.getLogger(__name__)


class PlaywrightCDPDriver(BrowserDriverPort):
    """基于 Playwright / 原生 Chromium CDP 的浏览器驱动器。

    特性：
    - 支持按 session_id 隔离 Page 与 CDP 会话；
    - 绑定 CDPScreencastRelay 实现实时推流；
    - 支持优雅资源释放（INV-BROWSER-05）。
    """

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 800,
    ) -> None:
        self.headless = headless
        self.default_width = viewport_width
        self.default_height = viewport_height
        self._sessions: dict[str, BrowserSessionSummary] = {}
        self._relays: dict[str, CDPScreencastRelay] = {}
        self._pages: dict[str, Any] = {}
        self._cdp_sessions: dict[str, Any] = {}
        self._browser: Any = None
        self._playwright: Any = None
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        run_id: str | None = None,
        initial_url: str = "about:blank",
    ) -> BrowserSessionSummary:
        """创建或复用浏览器会话。"""
        async with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id]

            relay = CDPScreencastRelay(session_id=session_id)
            self._relays[session_id] = relay

            summary = BrowserSessionSummary(
                session_id=session_id,
                run_id=run_id,
                url=initial_url,
                title="New Tab",
                status=BrowserSessionStatus.IDLE,
                viewport_width=self.default_width,
                viewport_height=self.default_height,
                has_active_stream=True,
            )
            self._sessions[session_id] = summary

            # 尝试连接底层真实 Playwright/Chromium 引擎（若可用）
            try:
                await self._init_cdp_for_session(session_id, initial_url)
            except Exception as e:
                logger.info("[PlaywrightCDPDriver] Playwright not launching live display (%s), running in resilient mode", e)

            return summary

    async def _init_cdp_for_session(self, session_id: str, url: str) -> None:
        """内部初始化 CDP 会话并开启 Screencast 帧监听。"""
        try:
            from playwright.async_api import async_playwright

            if self._playwright is None:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-gpu", "--no-sandbox"],
                )

            context = await self._browser.new_context(
                viewport={"width": self.default_width, "height": self.default_height}
            )
            page = await context.new_page()
            self._pages[session_id] = page

            cdp = await context.new_cdp_session(page)
            self._cdp_sessions[session_id] = cdp

            # 绑定 Page.screencastFrame 监听
            relay = self._relays.get(session_id)
            if relay:
                async def _on_screencast_frame(payload: dict[str, Any]) -> None:
                    try:
                        import base64
                        data_bytes = base64.b64decode(payload["data"])
                        await relay.emit_frame(data_bytes, payload.get("metadata"))
                        await cdp.send("Page.screencastFrameAck", {"sessionId": payload["sessionId"]})
                    except Exception as err:
                        logger.warning("[PlaywrightCDPDriver] Error handling screencast frame: %s", err)

                cdp.on("Page.screencastFrame", _on_screencast_frame)
                await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 75, "everyNthFrame": 1})

            if url and url != "about:blank":
                await page.goto(url)
                title = await page.title()
                if session_id in self._sessions:
                    old = self._sessions[session_id]
                    self._sessions[session_id] = BrowserSessionSummary(
                        session_id=old.session_id,
                        run_id=old.run_id,
                        url=url,
                        title=title or "Page",
                        status=old.status,
                        viewport_width=old.viewport_width,
                        viewport_height=old.viewport_height,
                        has_active_stream=True,
                    )
        except (ImportError, Exception) as exc:
            logger.debug("[PlaywrightCDPDriver] CDP init skipped: %s", exc)

    async def get_session(self, session_id: str) -> BrowserSessionSummary | None:
        return self._sessions.get(session_id)

    async def list_sessions(self) -> list[BrowserSessionSummary]:
        return list(self._sessions.values())

    async def close_session(self, session_id: str) -> bool:
        """优雅关闭会话并清理 CDP / Page 资源（INV-BROWSER-05）。"""
        async with self._lock:
            if session_id not in self._sessions:
                return False

            relay = self._relays.pop(session_id, None)
            if relay:
                await relay.close()

            cdp = self._cdp_sessions.pop(session_id, None)
            if cdp:
                with contextlib.suppress(Exception):
                    await cdp.detach()

            page = self._pages.pop(session_id, None)
            if page:
                with contextlib.suppress(Exception):
                    await page.close()

            self._sessions.pop(session_id, None)
            return True

    async def navigate(self, session_id: str, url: str) -> BrowserSessionSummary:
        """控制指定会话导航至目标网页。"""
        summary = self._sessions.get(session_id)
        if summary is None:
            summary = await self.create_session(session_id=session_id, initial_url=url)

        page = self._pages.get(session_id)
        title = "Navigated Page"
        if page is not None:
            try:
                await page.goto(url)
                title = await page.title()
            except Exception as e:
                logger.warning("[PlaywrightCDPDriver] Navigation error: %s", e)

        updated = BrowserSessionSummary(
            session_id=summary.session_id,
            run_id=summary.run_id,
            url=url,
            title=title,
            status=summary.status,
            viewport_width=summary.viewport_width,
            viewport_height=summary.viewport_height,
            has_active_stream=summary.has_active_stream,
        )
        self._sessions[session_id] = updated

        relay = self._relays.get(session_id)
        if relay:
            await relay.emit_metadata({"url": url, "title": title})

        return updated

    async def dispatch_input(self, session_id: str, event: BrowserInputEvent) -> bool:
        """向底层 CDP 注入鼠标或键盘事件。"""
        cdp = self._cdp_sessions.get(session_id)
        if cdp is None:
            return True

        try:
            summary = self._sessions.get(session_id)
            width = summary.viewport_width if summary else self.default_width
            height = summary.viewport_height if summary else self.default_height

            x = event.x if event.x > 1.0 else event.x * width
            y = event.y if event.y > 1.0 else event.y * height

            if event.type == BrowserInputEventType.MOUSE_MOVE:
                await cdp.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            elif event.type == BrowserInputEventType.MOUSE_DOWN:
                btn = event.button or "left"
                await cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": btn, "clickCount": 1})
            elif event.type == BrowserInputEventType.MOUSE_UP:
                btn = event.button or "left"
                await cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": btn, "clickCount": 1})
            elif event.type == BrowserInputEventType.WHEEL:
                await cdp.send("Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": event.delta_x, "deltaY": event.delta_y})
            elif event.type == BrowserInputEventType.KEY_DOWN:
                params = {"type": "keyDown"}
                if event.key:
                    params["key"] = event.key
                if event.code:
                    params["code"] = event.code
                await cdp.send("Input.dispatchKeyEvent", params)
            elif event.type == BrowserInputEventType.KEY_UP:
                params = {"type": "keyUp"}
                if event.key:
                    params["key"] = event.key
                if event.code:
                    params["code"] = event.code
                await cdp.send("Input.dispatchKeyEvent", params)
            return True
        except Exception as e:
            logger.warning("[PlaywrightCDPDriver] Failed to dispatch input: %s", e)
            return False

    def get_relay(self, session_id: str) -> CDPScreencastRelay | None:
        return self._relays.get(session_id)

    async def close_all(self) -> None:
        """关闭所有浏览器会话并关闭底层浏览器实例。"""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.close_session(sid)
        if self._browser:
            with contextlib.suppress(Exception):
                await self._browser.close()
        if self._playwright:
            with contextlib.suppress(Exception):
                await self._playwright.stop()


__all__ = ["PlaywrightCDPDriver"]
