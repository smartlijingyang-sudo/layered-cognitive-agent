"""Browser driver port protocol definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from lca.contracts.models.browser.stream import (
        BrowserInputEvent,
        BrowserSessionSummary,
    )
    from lca.infrastructure.browser.screencast_relay import CDPScreencastRelay


class BrowserDriverPort(Protocol):
    """浏览器驱动核心端口协议（屏蔽具体 Playwright/CDP 实现细节）。"""

    async def create_session(
        self,
        session_id: str,
        run_id: str | None = None,
        initial_url: str = "about:blank",
    ) -> BrowserSessionSummary:
        """创建或分配一个隔离的浏览器会话。"""
        ...

    async def get_session(self, session_id: str) -> BrowserSessionSummary | None:
        """获取指定会话最新状态。"""
        ...

    async def list_sessions(self) -> list[BrowserSessionSummary]:
        """列出当前所有活跃的浏览器会话。"""
        ...

    async def close_session(self, session_id: str) -> bool:
        """安全关闭浏览器会话并释放资源。"""
        ...

    async def navigate(self, session_id: str, url: str) -> BrowserSessionSummary:
        """控制指定会话导航至目标网页。"""
        ...

    async def dispatch_input(self, session_id: str, event: BrowserInputEvent) -> bool:
        """向浏览器分发底层输入事件（鼠标移动/点击/滚轮/键盘按键）。"""
        ...

    def get_relay(self, session_id: str) -> CDPScreencastRelay | None:
        """获取会话对应的 Screencast 帧中继器。"""
        ...


__all__ = ["BrowserDriverPort"]
