"""Playwright & Chrome DevTools Protocol (CDP) Browser Driver implementation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

from lca.contracts.models.browser.stream import (
    BrowserInputEvent,
    BrowserInputEventType,
    BrowserSessionStatus,
    BrowserSessionSummary,
)
from lca.contracts.protocols.browser import BrowserDriverPort
from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay

logger = logging.getLogger(__name__)


def choose_chromium_proxy(env_server: str, *, mihomo_open: bool) -> str:
    """Pick a proxy Chrome can actually CONNECT through.

    The process proxy on port 7890 accepts curl and resets Chrome
    (``net::ERR_CONNECTION_CLOSED``). When mihomo is listening on 7891, use that.
    """
    if env_server.rstrip("/").endswith(":7890") and mihomo_open:
        return "http://127.0.0.1:7891"
    return env_server


def _mihomo_proxy_open() -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 7891), timeout=0.2):
            return True
    except OSError:
        return False


def _chromium_proxy() -> dict[str, str] | None:
    """Chromium does not use the process proxy unless launch sets it."""
    server = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or ""
    if not server:
        return None
    server = choose_chromium_proxy(server, mihomo_open=_mihomo_proxy_open())
    proxy = {"server": server}
    bypass = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    if bypass:
        proxy["bypass"] = bypass
    return proxy


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
        arbitration_engine: BrowserArbitrationEngine | None = None,
    ) -> None:
        self.headless = headless
        self.default_width = viewport_width
        self.default_height = viewport_height
        self.arbitration_engine = arbitration_engine
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
                logger.info(
                    "[PlaywrightCDPDriver] Playwright not launching live display (%s), running in resilient mode",
                    e,
                )

            # 返回可能已被 _init_cdp_for_session 更新的实时摘要（含真实页面标题）。
            return self._sessions[session_id]

    async def _init_cdp_for_session(self, session_id: str, url: str) -> None:
        """内部初始化 CDP 会话并开启 Screencast 帧监听。"""
        try:
            from playwright.async_api import async_playwright

            if self._playwright is None:
                self._playwright = await async_playwright().start()
                launch_kwargs: dict[str, Any] = {
                    "headless": self.headless,
                    "args": ["--disable-gpu", "--no-sandbox"],
                }
                proxy = _chromium_proxy()
                if proxy is not None:
                    launch_kwargs["proxy"] = proxy
                from pathlib import Path

                candidates = [
                    Path("/home/lichao/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"),
                    Path(
                        "/home/lichao/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell"
                    ),
                    Path("/usr/bin/google-chrome"),
                    Path("/usr/bin/chromium-browser"),
                    Path("/usr/bin/chromium"),
                ]
                for cand in candidates:
                    if cand.is_file():
                        launch_kwargs["executable_path"] = str(cand)
                        break

                try:
                    self._browser = await self._playwright.chromium.launch(**launch_kwargs)
                except Exception:
                    launch_kwargs.pop("executable_path", None)
                    self._browser = await self._playwright.chromium.launch(**launch_kwargs)
            elif self._browser is not None and not self._browser.is_connected():
                self._pages.clear()
                self._cdp_sessions.clear()
                relaunch: dict[str, Any] = {
                    "headless": self.headless,
                    "args": ["--disable-gpu", "--no-sandbox"],
                }
                proxy = _chromium_proxy()
                if proxy is not None:
                    relaunch["proxy"] = proxy
                self._browser = await self._playwright.chromium.launch(**relaunch)

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
                        await cdp.send(
                            "Page.screencastFrameAck", {"sessionId": payload["sessionId"]}
                        )
                    except Exception as err:
                        logger.warning(
                            "[PlaywrightCDPDriver] Error handling screencast frame: %s", err
                        )

                cdp.on("Page.screencastFrame", _on_screencast_frame)
                await cdp.send(
                    "Page.startScreencast", {"format": "jpeg", "quality": 75, "everyNthFrame": 1}
                )

            if url and url != "about:blank":
                title = "Page"
                try:
                    await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                    title = await page.title()
                except Exception as goto_err:
                    logger.warning(
                        "[PlaywrightCDPDriver] page.goto failed for %s: %s", url, goto_err
                    )

                if session_id in self._sessions:
                    old = self._sessions[session_id]
                    # RA-155: has_active_stream=True 显式保留 —— 上方 Page.startScreencast
                    # 刚开启 screencast 流，这里是唯一知道流已建立的地方，
                    # 不是旧代码的漂移（navigate 处则保留旧值）。
                    self._sessions[session_id] = old.model_copy(
                        update={"url": url, "title": title or "Page", "has_active_stream": True}
                    )
        except (ImportError, Exception) as exc:
            logger.warning("[PlaywrightCDPDriver] CDP init skipped: %s", exc)

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

    def has_page(self, session_id: str) -> bool:
        """True when this session still has a live Playwright page."""
        page = self._pages.get(session_id)
        if page is None:
            return False
        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed) and is_closed():
            self._pages.pop(session_id, None)
            self._cdp_sessions.pop(session_id, None)
            return False
        return True

    async def _open_missing_page(self, session_id: str, url: str) -> None:
        """Recreate the page for a session record whose browser page is gone."""
        async with self._lock:
            if self.has_page(session_id):
                return
            if session_id not in self._relays:
                self._relays[session_id] = CDPScreencastRelay(session_id=session_id)
            await self._init_cdp_for_session(session_id, url)

    async def push_snapshot(self, session_id: str) -> bool:
        """Send one JPEG of the current page to connected preview clients.

        Headless Chrome often emits no further screencast frames after the
        first ones were dropped because no viewer was connected yet.
        """
        page = self._pages.get(session_id)
        relay = self._relays.get(session_id)
        if page is None or relay is None or relay.client_count == 0:
            return False
        try:
            jpeg = await page.screenshot(type="jpeg", quality=70)
        except Exception as exc:
            logger.warning("[PlaywrightCDPDriver] snapshot failed for %s: %s", session_id, exc)
            return False
        if not isinstance(jpeg, (bytes, bytearray)) or not jpeg:
            return False
        return await relay.emit_frame(bytes(jpeg))

    async def navigate(self, session_id: str, url: str) -> BrowserSessionSummary:
        """控制指定会话导航至目标网页。"""
        summary = self._sessions.get(session_id)
        if summary is None:
            summary = await self.create_session(session_id=session_id, initial_url=url)
            if self.has_page(session_id):
                await self.push_snapshot(session_id)
                return summary

        if self._pages.get(session_id) is None:
            await self._open_missing_page(session_id, url)
            reopened = self._sessions.get(session_id)
            if reopened is not None and self.has_page(session_id):
                await self.push_snapshot(session_id)
                return reopened

        page = self._pages.get(session_id)
        # RA-153: 导航失败时不伪造 "Navigated Page" 标题。title 在 contracts 里是
        # 必填 str（BrowserSessionSummary，改 contract 超出本轮 scope），所以
        # goto 失败时保留导航前的已有标题 —— 不宣称一次并未确认发生的成功导航。
        title = summary.title
        if page is not None:
            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                title = await page.title()
            except Exception as e:
                logger.warning("[PlaywrightCDPDriver] Navigation error: %s", e)

        updated = summary.model_copy(update={"url": url, "title": title})
        self._sessions[session_id] = updated

        relay = self._relays.get(session_id)
        if relay:
            await relay.emit_metadata({"url": url, "title": title})

        await self.push_snapshot(session_id)
        return updated

    async def click(self, session_id: str, selector: str) -> bool:
        """Click a CSS/XPath selector in the live page for a session."""
        page = self._pages.get(session_id)
        if page is None:
            return False
        try:
            await page.locator(selector).click(timeout=10000)
            return True
        except Exception as exc:
            logger.warning("[PlaywrightCDPDriver] click failed for %s: %s", session_id, exc)
            return False

    async def type_text(self, session_id: str, selector: str, text: str) -> bool:
        """Fill text into a live page input; falls back to click + keyboard typing."""
        page = self._pages.get(session_id)
        if page is None:
            return False
        locator = page.locator(selector)
        try:
            await locator.fill(text, timeout=10000)
            return True
        except Exception:
            try:
                await locator.click(timeout=5000)
                await page.keyboard.type(text)
                return True
            except Exception as exc:
                logger.warning("[PlaywrightCDPDriver] type failed for %s: %s", session_id, exc)
                return False

    async def extract_text(self, session_id: str) -> str:
        """Return the visible body text of the live page (empty string when not live)."""
        page = self._pages.get(session_id)
        if page is None:
            return ""
        try:
            return (await page.locator("body").inner_text()) or ""
        except Exception as exc:
            logger.warning("[PlaywrightCDPDriver] extract_text failed for %s: %s", session_id, exc)
            return ""

    async def take_screenshot(self, session_id: str) -> bytes | None:
        """Capture a JPEG screenshot of the live page; None when not live."""
        page = self._pages.get(session_id)
        if page is None:
            return None
        try:
            shot = await page.screenshot(type="jpeg", quality=70)
            return bytes(shot) if shot else None
        except Exception as exc:
            logger.warning("[PlaywrightCDPDriver] screenshot failed for %s: %s", session_id, exc)
            return None

    async def find_text(self, session_id: str, query: str, case_sensitive: bool = False) -> int:
        """Count occurrences of query in the live page body text (0 when not live)."""
        if not query:
            return 0
        text = await self.extract_text(session_id)
        if not text:
            return 0
        if case_sensitive:
            return text.count(query)
        return text.lower().count(query.lower())

    async def dispatch_input(self, session_id: str, event: BrowserInputEvent) -> bool:
        """向底层 CDP 注入鼠标或键盘事件；无 CDP 会话时返回 False。"""
        if self.arbitration_engine is not None:
            decision = self.arbitration_engine.evaluate_input(session_id, event)
            if not decision.allowed:
                return False

        cdp = self._cdp_sessions.get(session_id)
        if cdp is None:
            # RA-150: 无 CDP 会话时输入无处可送，fail-closed 返回 False 并记日志，
            # 与 arbitration 拒绝同语义；绝不伪造"已派发"成功。
            logger.warning(
                "[PlaywrightCDPDriver] dispatch_input dropped: no CDP session for %s",
                session_id,
            )
            return False

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
                await cdp.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mousePressed", "x": x, "y": y, "button": btn, "clickCount": 1},
                )
            elif event.type == BrowserInputEventType.MOUSE_UP:
                btn = event.button or "left"
                await cdp.send(
                    "Input.dispatchMouseEvent",
                    {"type": "mouseReleased", "x": x, "y": y, "button": btn, "clickCount": 1},
                )
            elif event.type == BrowserInputEventType.WHEEL:
                await cdp.send(
                    "Input.dispatchMouseEvent",
                    {
                        "type": "mouseWheel",
                        "x": x,
                        "y": y,
                        "deltaX": event.delta_x,
                        "deltaY": event.delta_y,
                    },
                )
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


_SHARED_BROWSER_DRIVER: PlaywrightCDPDriver | None = None


def get_shared_browser_driver() -> PlaywrightCDPDriver:
    """获取进程级全局共享的 PlaywrightCDPDriver 单例。"""
    global _SHARED_BROWSER_DRIVER
    if _SHARED_BROWSER_DRIVER is None:
        _SHARED_BROWSER_DRIVER = PlaywrightCDPDriver()
    return _SHARED_BROWSER_DRIVER


def set_shared_browser_driver(driver: PlaywrightCDPDriver | None) -> None:
    """设置或重置全局共享驱动单例（主要用于测试与隔离注入）。"""
    global _SHARED_BROWSER_DRIVER
    _SHARED_BROWSER_DRIVER = driver


__all__ = [
    "PlaywrightCDPDriver",
    "get_shared_browser_driver",
    "set_shared_browser_driver",
]
