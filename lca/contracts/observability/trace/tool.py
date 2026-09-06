"""TraceTool Protocol（ADR-0063 PR-9）。

把 ``TraceInspector`` 的 5 个方法各自注册为 ``tools`` seam 中的工具；
Coding Agent 可通过标准 tool 接口调用，不需要碰 Python API。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TraceTool(Protocol):
    """单一 trace 工具；invoke(**kwargs) 返回可序列化的 dict。"""

    @property
    def name(self) -> str:
        """工具注册名（kebab-case，如 ``inspect-trace``）。"""

    @property
    def description(self) -> str:
        """工具用途说明（传给 Coding Agent）。"""

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        """执行工具；返回 JSON-serializable dict。

        参数语义依赖具体工具；events 不传时使用 TraceInspector.events。
        """
