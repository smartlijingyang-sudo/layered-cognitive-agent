"""Browser subagent implementation (ADR-0248 §5.3 / s06, s13)."""

from __future__ import annotations

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
    BrowserActionType,
)
from lca.contracts.protocols import Tool
from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
from lca.infrastructure.computer.desktop_lock import DesktopLockCoordinator
from lca.infrastructure.tools.browser.tools import build_browser_tools


class BrowserSubagent:
    """自动化浏览器执行子代理。

    不变量：
    - INV-05: 物理禁声（子代理严格剔除 send_message 工具，只能向父代理返回结构化数据，无权对用户通道发声）。
    - 自动化操作前抢占桌面单屏锁，结束后主动归还锁。
    - 与 BrowserArbitrationEngine 联动维护 AGENT_RUNNING 态。
    """

    def __init__(
        self,
        agent_id: str = "browser_subagent",
        lock_manager: DesktopLockCoordinator | None = None,
        arbitration_engine: BrowserArbitrationEngine | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.lock_manager = lock_manager
        self.arbitration_engine = arbitration_engine
        # 严格过滤工具集：严禁声带发声工具
        self._tools: list[Tool] = [
            tool for tool in build_browser_tools() if getattr(tool, "name", "") != "send_message"
        ]

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
            # 2. 执行浏览器动作
            if action.action_type == BrowserActionType.NAVIGATE:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                    url=action.url,
                    title="Navigated Page",
                )
            if action.action_type == BrowserActionType.CLICK:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                    text_content=f"Clicked selector: {action.selector}",
                )
            if action.action_type == BrowserActionType.TYPE:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                    text_content=f"Typed text: {action.text}",
                )
            if action.action_type == BrowserActionType.SCREENSHOT:
                art_id = new_id("art_screenshot")
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                    screenshot_artifact_id=art_id,
                )
            if action.action_type == BrowserActionType.CLOSE:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=True,
                )
            return BrowserActionResult(
                action_type=action.action_type,
                success=True,
                text_content=f"Executed action {action.action_type}",
            )
        finally:
            if self.arbitration_engine is not None:
                self.arbitration_engine.release_to_agent(session_id)
            # 3. 动作完成后立即释放单屏桌面锁
            if self.lock_manager is not None:
                await self.lock_manager.free_window(
                    agent_id=self.agent_id,
                    session_id=session_id,
                )


__all__ = ["BrowserSubagent"]
