"""ComponentRegistry —— 通用组件注册表，按 (category, name) 注册/解析实现。"""

from __future__ import annotations

from typing import Any


class ComponentRegistry:
    """按 (category, name) 注册和解析组件实现。

    category 例如 "observability"、"memory"、"state_store" 等；
    name 是用户可见的实现名称，例如 "console"、"simple" 等。
    值可以是类（无参构造）或工厂函数（接受上下文参数）。
    """

    def __init__(self) -> None:
        self._registries: dict[str, dict[str, Any]] = {}

    def register(self, category: str, name: str, impl: Any) -> None:
        self._registries.setdefault(category, {})[name] = impl

    def resolve(self, category: str, name: str) -> Any | None:
        return self._registries.get(category, {}).get(name)

    def list(self, category: str) -> list[str]:
        return list(self._registries.get(category, {}).keys())

    def get_registry(self, category: str) -> dict[str, Any]:
        return self._registries.get(category, {})


_global_registry = ComponentRegistry()


def get_global_registry() -> ComponentRegistry:
    return _global_registry
