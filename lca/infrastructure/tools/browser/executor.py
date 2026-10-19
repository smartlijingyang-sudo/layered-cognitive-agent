"""Browser action executor: the shared execution seam behind BrowserSubagent.

Routes ``BrowserAction`` dispatch through the real browser tools built by
``build_browser_tools`` so that ``BrowserSubagent.execute_action`` performs
real executions instead of fabricated results (RA-146). Actions with no
backing tool fail closed with an honest ``success=False`` result.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
)
from lca.contracts.protocols import Tool
from lca.infrastructure.tools.browser.tools import build_browser_tools

logger = logging.getLogger(__name__)

# BrowserActionType -> 真实浏览器工具名（共享执行 seam）。
_ACTION_TOOL_NAMES: dict[BrowserActionType, str] = {
    BrowserActionType.NAVIGATE: "browser_navigate",
    BrowserActionType.CLICK: "browser_click",
    BrowserActionType.TYPE: "browser_type",
    BrowserActionType.SCREENSHOT: "browser_screenshot",
    BrowserActionType.EXTRACT_TEXT: "browser_extract_text",
    BrowserActionType.CLOSE: "browser_close",
}

_RESULT_FIELDS = frozenset(BrowserActionResult.model_fields)


def _args_for(action: BrowserAction) -> dict[str, Any]:
    """BrowserAction 载荷 -> 浏览器工具参数（只传非空字段）。"""
    args: dict[str, Any] = {}
    if action.url is not None:
        args["url"] = action.url
    if action.selector is not None:
        args["selector"] = action.selector
    if action.text is not None:
        args["text"] = action.text
    return args


def _result_from_observation(
    action: BrowserAction, observation: Any
) -> BrowserActionResult:
    """Observation -> BrowserActionResult：工具已把 res.model_dump() 放进 payload，
    优先恢复真实结果；恢复失败则回退为诚实的文本结果。"""
    payload = getattr(observation, "payload", None)
    if isinstance(payload, dict):
        data = {k: v for k, v in payload.items() if k in _RESULT_FIELDS}
        try:
            result = BrowserActionResult.model_validate(data)
            if result.action_type != action.action_type:
                result = result.model_copy(update={"action_type": action.action_type})
            return result
        except Exception:
            logger.debug("payload 不是合法的 BrowserActionResult，回退为文本结果", exc_info=True)
    return BrowserActionResult(
        action_type=action.action_type,
        success=bool(getattr(observation, "success", False)),
        text_content=str(payload),
        error=getattr(observation, "error", None),
    )


def build_browser_action_executor(
    tools: Sequence[Tool] | None = None,
    driver: Any | None = None,
    session_id: str | None = None,
) -> Callable[[BrowserAction], Awaitable[BrowserActionResult]]:
    """构建浏览器动作执行器：把 BrowserAction 分发到真实的浏览器工具。

    :param tools: 显式工具集；不传则用 build_browser_tools(driver) 构建。
    :param driver: 透传给 build_browser_tools 的 CDP 驱动。
    :param session_id: 透传给各浏览器工具的会话 ID（RA-154：subagent driver
        直驱路径用；不传则工具按各自缺省处理）。
    """
    tool_list = list(tools) if tools is not None else build_browser_tools(driver)
    by_name = {getattr(tool, "name", ""): tool for tool in tool_list}

    async def execute(action: BrowserAction) -> BrowserActionResult:
        tool_name = _ACTION_TOOL_NAMES.get(action.action_type)
        tool = by_name.get(tool_name) if tool_name else None
        if tool is None:
            return BrowserActionResult(
                action_type=action.action_type,
                success=False,
                error=f"没有浏览器工具支撑动作 '{action.action_type.value}'",
            )
        args = _args_for(action)
        if session_id is not None:
            args["session_id"] = session_id
        try:
            observation = await tool.execute(args)
        except Exception as exc:
            logger.warning("浏览器工具 %s 执行异常: %s", tool_name, exc)
            return BrowserActionResult(
                action_type=action.action_type,
                success=False,
                error=f"浏览器工具 '{tool_name}' 执行异常: {exc}",
            )
        return _result_from_observation(action, observation)

    return execute


__all__ = ["build_browser_action_executor"]
