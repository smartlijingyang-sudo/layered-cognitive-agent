"""Browser subagent implementation (ADR-0248 §5.3 / s06, s13)."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable

from lca.contracts.models.browser.models import (
    BrowserAction,
    BrowserActionResult,
)
from lca.contracts.protocols import Tool
from lca.infrastructure.browser.arbitration import BrowserArbitrationEngine
from lca.infrastructure.computer.desktop_lock import DesktopLockCoordinator

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
    - 动作分发走注入的 action_executor（共享浏览器执行 seam）；本模块不再伪造
      任何执行结果（RA-146）。
    """

    def __init__(
        self,
        agent_id: str = "browser_subagent",
        tools: Iterable[Tool] | None = None,
        action_executor: ActionExecutor | None = None,
        lock_manager: DesktopLockCoordinator | None = None,
        arbitration_engine: BrowserArbitrationEngine | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.lock_manager = lock_manager
        self.arbitration_engine = arbitration_engine
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
        """在单屏互斥锁保护下执行单步浏览器操作，分发走注入的 executor。"""
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
            # 2. 分发到注入的共享执行 seam（RA-146：不再伪造结果）
            if self._executor is None:
                return BrowserActionResult(
                    action_type=action.action_type,
                    success=False,
                    error="未注入 action_executor，无法执行浏览器动作",
                )
            dispatched = self._executor(action)
            if inspect.isawaitable(dispatched):
                return await dispatched
            return dispatched
        finally:
            if self.arbitration_engine is not None:
                self.arbitration_engine.release_to_agent(session_id)
            # 3. 动作完成后立即释放单屏桌面锁
            if self.lock_manager is not None:
                await self.lock_manager.free_window(
                    agent_id=self.agent_id,
                    session_id=session_id,
                )


__all__ = ["ActionExecutor", "BrowserSubagent"]
