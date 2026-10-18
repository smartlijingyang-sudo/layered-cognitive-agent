"""Driver-injected base tool for the Muse Browser tool suite (RA-151).

"同类家园"：六个工具类逐字重复的 __init__(driver) + _get_driver() 收敛到此。
get_shared_browser_driver 的懒导入必须保留在函数内（避免 infrastructure.browser
与 tools.browser 的导入时循环，见 BrowserSearchTool 处的注释）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.protocols import Tool

if TYPE_CHECKING:
    from lca.infrastructure.browser.cdp_driver import PlaywrightCDPDriver


class _DriverInjectedTool(Tool):
    """携带共享 driver 注入 seam 的工具基类：构造注入优先，缺省回落共享单例。"""

    def __init__(self, driver: PlaywrightCDPDriver | None = None) -> None:
        self._driver = driver

    def _get_driver(self) -> PlaywrightCDPDriver:
        if self._driver is not None:
            return self._driver
        from lca.infrastructure.browser.cdp_driver import get_shared_browser_driver

        return get_shared_browser_driver()


def browser_preview_widget_tag(session_id: str, url: str, title: str, status: str) -> str:
    """拼装 [widget:browser_preview?...] 预览卡片标签（open / transfer 工具共用）。"""
    return f"[widget:browser_preview?sessionId={session_id}&url={url}&title={title}&status={status}]"
