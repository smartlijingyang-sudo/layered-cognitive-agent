"""工具注册表 —— 策略模式管理工具集合。"""

from __future__ import annotations

from lca.contracts.protocols import Tool, ToolRegistry


class SimpleToolRegistry(ToolRegistry):
    """按名称注册和查找工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)
