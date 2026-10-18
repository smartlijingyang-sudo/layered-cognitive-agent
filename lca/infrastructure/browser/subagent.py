"""Browser subagent implementation (ADR-0248 §5.3 / s06, s13)."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import TYPE_CHECKING

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
)
from lca.contracts.protocols import Tool
from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
from lca.infrastructure.computer.desktop_lock import DesktopLockCoordinator

if TYPE_CHECKING:
    from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver

logger = logging.getLogger(__name__)

# 动作执行器：共享浏览器执行 seam，由调用方经构造函数注入。
# 同步或异步可调用对象：(BrowserAction) -> BrowserActionResult。
ActionExecutor = Callable[
    [BrowserAction], "BrowserActionResult | Awaitable[BrowserActionResult]"
]

_VOCAL_TOOL_NAMES = frozenset({"send_message"})


class BrowserSubagent:
    """自动化浏览器执行子代理。

    不变量：
    - INV-05: 物理禁声（注入的工具集仍经过 send_message 过滤，子代理只能向父代理
      返回结构化数据，无权对用户通道发声）。
    - 自动化操作前抢占桌面单屏锁，结束后主动归还锁。
    - 与 BrowserArbitrationEngine 联动维护 AGENT_RUNNING 态。
    - 执行分发三层（RA-146）：显式注入的 action_executor（共享执行 seam）优先；
      其次 driver 直驱真执行；两者皆无则 fail-closed——本模块不再伪造任何执行结果。
    """

    def __init__(
        self,
        agent_id: str = "browser_subagent",
        tools: Iterable[Tool] | None = None,
        action_executor: ActionExecutor | None = None,
        lock_manager: DesktopLockCoordinator | None = None,
        arbitration_engine: BrowserArbitrationEngine | None = None,
        driver: PlaywrightCDPDriver | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.lock_manager = lock_manager
        self.arbitration_engine = arbitration_engine
        self.driver = driver
        # INV-05: 对注入的工具集强制物理剔除发声工具（调用方漏滤也不行）。
        self._tools: list[Tool] = [
            tool
            for tool in (tools or [])
            if getattr(tool, "name", "") not in _VOCAL_TOOL_NAMES
        ]
        self._executor = action_executor

    def get_tools(self) -> list[Tool]:
        """获取浏览器子代理挂载的工具集。保证 100% 无发声工具（INV-05）。"""
        return list(self._tools)

    async def execute_action(
        self,
        session_id: str,
        action: BrowserAction,
    ) -> BrowserActionResult:
        """在单屏互斥锁保护下执行单步浏览器操作。"""
        # 1. 尝试抢占单屏桌面独占锁
        if self.lock_manager is not None:
            acquired = await self.lock_manager.allocate_window(
                agent_id=self.agent_id,
                session_id=session_id,
                ttl_seconds=action.timeout_s + 10,
            )
            if not acquired:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=False,
                    error=f"桌面单屏锁正被其他任务占用 ({self.lock_manager.get_current_owner()})",
                )

        if self.arbitration_engine is not None:
            self.arbitration_engine.start_agent_task(session_id)

        try:
            # 2. 显式注入的共享执行 seam 优先（RA-146）
            if self._executor is not None:
                dispatched = self._executor(action)
                if inspect.isawaitable(dispatched):
                    return await dispatched
                return dispatched
            # 3. driver 直驱真执行（无显式 executor 时的兼容路径）
            if self.driver is not None:
                return await self._execute_via_driver(session_id, action)
            # 4. 两者皆无：fail-closed，绝不伪造执行结果（RA-146）
            return BrowserActionResult(
                action_type=action.action_type,
                success=False,
                error="未注入 action_executor 且未提供 driver，无法执行浏览器动作",
            )
        finally:
            if self.arbitration_engine is not None:
                self.arbitration_engine.release_to_agent(session_id)
            # 5. 动作完成后立即释放单屏桌面锁
            if self.lock_manager is not None:
                await self.lock_manager.free_window(
                    agent_id=self.agent_id,
                    session_id=session_id,
                )

    async def _execute_via_driver(
        self,
        session_id: str,
        action: BrowserAction,
    ) -> BrowserActionResult:
        """driver 直驱真执行：无显式 executor 时的兼容路径（真执行，不伪造）。"""
        if action.action_type == BrowserActionType.NAVIGATE:
            try:
                summary = await self.driver.navigate(
                    session_id, action.url or "about:blank"
                )
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                    session_id=session_id,
                    url=summary.url,
                    title=summary.title,
                )
            except Exception as exc:
                logger.warning("[BrowserSubagent] live navigate failed: %s", exc)
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=False,
                    error=str(exc),
                )
        if action.action_type == BrowserActionType.CLICK:
            clicked = False
            if action.selector:
                try:
                    clicked = await self.driver.click(session_id, action.selector)
                except Exception as exc:
                    logger.warning("[BrowserSubagent] live click failed: %s", exc)
                    clicked = False
            return BrowserActionResult(
                action_type=action.action_type,
                success=clicked,
                text_content=f"Clicked selector: {action.selector}",
                details={"live": clicked},
            )
        if action.action_type == BrowserActionType.TYPE:
            typed = False
            if action.selector:
                try:
                    typed = await self.driver.type_text(
                        session_id, action.selector, action.text or ""
                    )
                except Exception as exc:
                    logger.warning("[BrowserSubagent] live type failed: %s", exc)
                    typed = False
            return BrowserActionResult(
                action_type=action.action_type,
                success=typed,
                text_content=f"Typed text into {action.selector}",
                details={"live": typed},
            )
        if action.action_type == BrowserActionType.SCREENSHOT:
            art_id = new_id("art_screenshot")
            try:
                shot = await self.driver.take_screenshot(session_id)
            except Exception as exc:
                logger.warning("[BrowserSubagent] live screenshot failed: %s", exc)
                shot = None
            if shot is not None:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                    screenshot_artifact_id=art_id,
                    details={"live": True, "screenshot_bytes": len(shot)},
                )
            return BrowserActionResult(
                action_type=action.action_type,
                success=False,
                screenshot_artifact_id=art_id,
                details={"live": False},
            )
        if action.action_type == BrowserActionType.EXTRACT_TEXT:
            try:
                text = await self.driver.extract_text(session_id)
            except Exception as exc:
                logger.warning("[BrowserSubagent] live extract failed: %s", exc)
                text = ""
            return BrowserActionResult(
                action_type=action.action_type,
                success=True,
                text_content=text or "",
                details={"live": bool(text)},
            )
        if action.action_type == BrowserActionType.CLOSE:
            try:
                closed = await self.driver.close_session(session_id)
            except Exception as exc:
                logger.warning("[BrowserSubagent] live close failed: %s", exc)
                closed = False
            return BrowserActionResult(
                action_type=action.action_type,
                success=closed,
                session_id=session_id,
            )
        return BrowserActionResult(
            action_type=action.action_type,
            success=False,
            error=f"driver 直驱不支持动作类型 '{action.action_type.value}'",
        )


__all__ = ["ActionExecutor", "BrowserSubagent"]
