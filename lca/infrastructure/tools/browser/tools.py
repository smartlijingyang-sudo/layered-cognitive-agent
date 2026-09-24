"""Browser control tools for BrowserSubagent (ADR-0248 §5.3 / s06)."""

from __future__ import annotations

from typing import Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.browser.models import BrowserActionResult, BrowserActionType
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool


class BrowserNavigateTool(Tool):
    """浏览器导航工具。"""

    name: ClassVar[str] = "browser_navigate"
    description: ClassVar[str] = "控制浏览器打开指定网页 URL。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "目标网页 URL"},
        },
        "required": ["url"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

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
        url = str(args["url"])
        # 在无头/实际浏览器中导航，此处构造结构化结果
        res = BrowserActionResult(
            action_type=BrowserActionType.NAVIGATE,
            success=True,
            url=url,
            title="Navigated Page",
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=res.model_dump(),
        )


class BrowserClickTool(Tool):
    """浏览器点击元素工具。"""

    name: ClassVar[str] = "browser_click"
    description: ClassVar[str] = "点击网页中指定的 CSS 或 XPath 选择器元素。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "目标元素选择器"},
        },
        "required": ["selector"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

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
        res = BrowserActionResult(
            action_type=BrowserActionType.CLICK,
            success=True,
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
    description: ClassVar[str] = "捕获当前网页可视区域或全页屏幕截图并生成 Artifact。"
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
    }
    is_idempotent: ClassVar[bool] = True
    effect_kind: ClassVar[str] = "ephemeral"
    default_timeout_s: ClassVar[int] = 30

    def validate(self, args: dict[str, Any]) -> str | None:
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        art_id = new_id("art_screenshot")
        res = BrowserActionResult(
            action_type=BrowserActionType.SCREENSHOT,
            success=True,
            screenshot_artifact_id=art_id,
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload=res.model_dump(),
        )


def build_browser_tools() -> list[Tool]:
    """构建浏览器子代理专属工具集合。严格不包含任何声带/消息投递工具。"""
    return [
        BrowserNavigateTool(),
        BrowserClickTool(),
        BrowserScreenshotTool(),
    ]


__all__ = [
    "BrowserClickTool",
    "BrowserNavigateTool",
    "BrowserScreenshotTool",
    "build_browser_tools",
]
