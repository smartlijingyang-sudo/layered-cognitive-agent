"""工具注册表 —— 策略模式管理工具集合。"""

from __future__ import annotations

from lca.contracts.protocols import Tool, ToolRegistry
from lca.layer0_infra.component_registry import NamedRegistry


class SimpleToolRegistry(NamedRegistry[Tool], ToolRegistry):
    """按名称注册和查找工具。"""

    _REGISTRY_KIND = "tool"

    def __init__(self) -> None:
        NamedRegistry.__init__(self)

    def register(self, tool: Tool) -> None:  # type: ignore[override]  # ToolRegistry 按 Tool 注册，NamedRegistry 按 (name, impl)
        self._entries[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._entries.get(name)
