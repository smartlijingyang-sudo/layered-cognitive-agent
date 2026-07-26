"""工具注册表 —— 策略模式管理工具集合。"""

from __future__ import annotations

from typing import Optional

from contracts.protocols import ToolProtocol


class SimpleToolRegistry:
    """按名称注册和查找工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolProtocol] = {}

    def register(self, tool: ToolProtocol) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolProtocol]:
        return self._tools.get(name)
