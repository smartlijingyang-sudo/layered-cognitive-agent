"""工具注册表 —— 策略模式管理工具集合。"""

from __future__ import annotations

from typing import Optional


class SimpleToolRegistry:
    """按名称注册和查找工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, object] = {}

    def register(self, tool: object) -> None:
        self._tools[tool.name] = tool  # type: ignore[attr-defined]

    def get(self, name: str) -> Optional[object]:
        return self._tools.get(name)
