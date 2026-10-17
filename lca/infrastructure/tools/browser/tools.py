"""Browser control tools for Agent & Subagent (ADR-0248 §5.3 / ADR-0280 / Muse Browser Spec)."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.browser.models import BrowserActionResult, BrowserActionType
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.browser.cdp_driver import (
    PlaywrightCDPDriver,
    get_shared_browser_driver,
)

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    """自动补齐缺少协议的 URL，默认补齐 https://。"""
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://", "about:", "chrome://")):
        return f"https://{cleaned}"
    return cleaned


class BrowserNavigateTool(Tool):
    """浏览器导航与页面打开工具。"""

    name: ClassVar[str] = "browser_navigate"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "在真实 Chromium 浏览器中打开指定网页，实时加载页面并生成预览卡片。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "目标网页 URL 或域名（例如 'https://news.ycombinator.com' 或 'muse.ai'）",
            },
            "session_id": {
                "type": "string",
                "description": "可选：指定复用的浏览器会话 ID。如果不提供将自动分配新会话",
            },
        },
        "required": ["url"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, driver: PlaywrightCDPDriver | None = None) -> None:
        self._driver = driver

    def _get_driver(self) -> PlaywrightCDPDriver:
        return self._driver or get_shared_browser_driver()

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("url") or not isinstance(args["url"], str):
            return "url 必填且为有效字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=err,
            )

        raw_url = str(args["url"])
        url = _normalize_url(raw_url)
        session_id = str(args.get("session_id") or new_id("brw"))

        driver = self._get_driver()
        try:
            # 若会话已存在则执行导航，否则新建会话并导航
            existing = await driver.get_session(session_id)
            if existing is not None:
                summary = await driver.navigate(session_id=session_id, url=url)
            else:
                summary = await driver.create_session(session_id=session_id, initial_url=url)
        except Exception as e:
            logger.warning("[BrowserNavigateTool] Browser driver failed: %s", e)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload={"session_id": session_id, "url": url, "error": str(e)},
                error=f"浏览器打开失败: {e}",
            )

        title = summary.title or "Web Page"
        final_url = summary.url or url
        widget_tag = f"[widget:browser_preview?sessionId={session_id}&url={final_url}&title={title}&status=agent_running]"
        text_content = f"已在真实浏览器中打开页面：{title} ({final_url})\n\n{widget_tag}"

        res = BrowserActionResult(
            action_type=BrowserActionType.NAVIGATE,
            success=True,
            session_id=session_id,
            url=final_url,
            title=title,
            text_content=text_content,
        )

        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                **res.model_dump(),
                "widget_tag": widget_tag,
            },
        )


class BrowserOpenTool(BrowserNavigateTool):
    """浏览器打开网页工具（别名，对齐 Muse / 业界标准命名）。"""

    name: ClassVar[str] = "browser_open"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = (
        "在真实浏览器中打开网页或链接并展示实时预览卡片（等同于 browser_navigate）。"
    )


class BrowserClickTool(Tool):
    """浏览器点击元素工具。"""

    name: ClassVar[str] = "browser_click"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "点击网页中指定的 CSS 或 XPath 选择器元素。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "目标元素选择器"},
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
        },
        "required": ["selector"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, driver: PlaywrightCDPDriver | None = None) -> None:
        self._driver = driver

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("selector") or not isinstance(args["selector"], str):
            return "selector 必填"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=err,
            )
        session_id = str(args.get("session_id") or "")
        res = BrowserActionResult(
            action_type=BrowserActionType.CLICK,
            success=True,
            session_id=session_id or None,
            text_content=f"Clicked: {args['selector']}",
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=res.model_dump(),
        )


class BrowserScreenshotTool(Tool):
    """浏览器截屏工具。"""

    name: ClassVar[str] = "browser_screenshot"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "捕获当前网页可视区域或全页屏幕截图并生成 Artifact。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "目标浏览器会话 ID"},
        },
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def __init__(self, driver: PlaywrightCDPDriver | None = None) -> None:
        self._driver = driver

    def validate(self, args: dict[str, Any]) -> str | None:
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        session_id = str(args.get("session_id") or "")
        art_id = new_id("art_screenshot")
        res = BrowserActionResult(
            action_type=BrowserActionType.SCREENSHOT,
            success=True,
            session_id=session_id or None,
            screenshot_artifact_id=art_id,
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=res.model_dump(),
        )


class BrowserCloseTool(Tool):
    """浏览器会话关闭工具。"""

    name: ClassVar[str] = "browser_close"
    namespace: ClassVar[str] = "browser"
    description: ClassVar[str] = "关闭指定的浏览器会话，释放 Chromium 页面与资源。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "要关闭的浏览器会话 ID"},
        },
        "required": ["session_id"],
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 10

    def __init__(self, driver: PlaywrightCDPDriver | None = None) -> None:
        self._driver = driver

    def _get_driver(self) -> PlaywrightCDPDriver:
        return self._driver or get_shared_browser_driver()

    def validate(self, args: dict[str, Any]) -> str | None:
        if not args.get("session_id") or not isinstance(args["session_id"], str):
            return "session_id 必填"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        err = self.validate(args)
        if err is not None:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=err,
            )
        session_id = str(args["session_id"])
        driver = self._get_driver()
        closed = await driver.close_session(session_id)
        res = BrowserActionResult(
            action_type=BrowserActionType.CLOSE,
            success=closed,
            session_id=session_id,
            text_content=f"Session {session_id} closed={closed}",
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=res.model_dump(),
        )


def build_browser_tools(driver: PlaywrightCDPDriver | None = None) -> list[Tool]:
    """构建浏览器能力工具集合。"""
    return [
        BrowserOpenTool(driver),
        BrowserNavigateTool(driver),
        BrowserClickTool(driver),
        BrowserScreenshotTool(driver),
        BrowserCloseTool(driver),
    ]


__all__ = [
    "BrowserClickTool",
    "BrowserCloseTool",
    "BrowserNavigateTool",
    "BrowserOpenTool",
    "BrowserScreenshotTool",
    "build_browser_tools",
]
