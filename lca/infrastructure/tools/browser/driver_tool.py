"""Driver-injected base tool for the Muse Browser tool suite (RA-151).

RA-157: 同家园新增 _UnimplementedTool —— fail-closed 占位工具的共享 honesty 基类。

"同类家园"：六个工具类逐字重复的 __init__(driver) + _get_driver() 收敛到此。
get_shared_browser_driver 的懒导入必须保留在函数内（避免 infrastructure.browser
与 tools.browser 的导入时循环，见 BrowserSearchTool 处的注释）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
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


logger = logging.getLogger(__name__)


class _UnimplementedTool(Tool):
    """Fail-closed 占位工具基类（RA-157）：后端尚未实现时诚实拒绝，绝不伪造"已运行/已派发"回执。

    子类只声明两个 ClassVar 契约：
    - _log_tag：日志标签（如 "[BrowserSpawnTaskTool]"）
    - _not_implemented_error：返回给调用方的错误文案
      （success=False Observation.error，含"尚未实现"）
    日志的 args 摘要由子类通过 _log_detail(args) 提供。

    构造兼容 _DriverInjectedTool(driver=None)：生产侧 build_browser_tools
    历史上传 driver 构造占位工具，基类收下但不用 ——
    fail-closed 工具不需要 driver。
    """

    _log_tag: ClassVar[str] = ""
    _not_implemented_error: ClassVar[str] = ""

    def __init__(self, driver: PlaywrightCDPDriver | None = None) -> None:
        self._driver = driver

    def _log_detail(self, args: dict[str, Any]) -> str:
        """日志里的参数摘要（子类覆盖）。"""
        return ""

    async def execute(self, args: dict[str, Any]) -> Observation:
        logger.warning("%s not implemented: %s", self._log_tag, self._log_detail(args))
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=self._not_implemented_error,
        )


def browser_preview_widget_tag(session_id: str, url: str, title: str, status: str) -> str:
    """拼装 [widget:browser_preview?...] 预览卡片标签（open / transfer 工具共用）。"""
    return f"[widget:browser_preview?sessionId={session_id}&url={url}&title={title}&status={status}]"
