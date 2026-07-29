"""注册表基础设施 —— ComponentRegistry + NamedRegistry 泛型基类。

语义约定（PR-5）：
- ``get`` / 软查询：找不到返回 None
- ``resolve`` / ``require``：找不到 raise RegistryKeyError
- NamedRegistry.resolve 始终 raise（历史行为）
- ComponentRegistry.resolve 为兼容仍返回 None；新代码优先用 require
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from lca.contracts.mechanisms import NamedRegistryProtocol

_T = TypeVar("_T")
_StrList = list[str]  # 避免类内方法名 list 遮蔽内置 list 类型


class RegistryKeyError(ValueError):
    """按名称查找注册表条目失败。

    继承 ValueError 以保持向后兼容（已有测试 assertRaises(ValueError)）。
    """

    def __init__(self, key: str, registry_kind: str, available: list[str]) -> None:
        self.key = key
        self.registry_kind = registry_kind
        self.available = available
        super().__init__(f"未注册{registry_kind} {key!r}，可用: {available}")


class NamedRegistry(NamedRegistryProtocol, Generic[_T]):
    """按名称注册和解析实体的泛型基类。

    子类通过 ``_REGISTRY_KIND`` 声明种类名（用于错误消息），
    可选择覆盖 ``resolve()`` 以改变解析语义（如工厂调用、类型转换）。
    """

    _REGISTRY_KIND: str = "条目"

    def __init__(self) -> None:
        self._entries: dict[str, _T] = {}

    def register(self, name: str, impl: _T) -> None:
        self._entries[name] = impl

    def get(self, name: str) -> _T | None:
        """软查询：找不到返回 None。"""
        return self._entries.get(name)

    def resolve(self, name: str) -> _T:
        impl = self._entries.get(name)
        if impl is None:
            raise RegistryKeyError(name, self._REGISTRY_KIND, self.list())
        return impl

    def list(self) -> _StrList:
        return list(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._entries


class ComponentRegistry:
    """按 (category, name) 注册和解析组件实现（发现型注册表）。

    category 例如 "observability"、"memory"、"state_store" 等；
    name 是用户可见的实现名称，例如 "console"、"simple" 等。
    值可以是类（无参构造）或工厂函数（接受上下文参数）。

    运行时绑定型注册表（Action / Tool / Transport）应由 AgentAssembly 注入实例，
    不要用全局 ComponentRegistry 承载。
    """

    def __init__(self) -> None:
        self._registries: dict[str, dict[str, Any]] = {}

    def register(self, category: str, name: str, impl: Any) -> None:
        self._registries.setdefault(category, {})[name] = impl

    def get(self, category: str, name: str) -> Any | None:
        """软查询：找不到返回 None。"""
        return self._registries.get(category, {}).get(name)

    def resolve(self, category: str, name: str) -> Any | None:
        """兼容别名：等同 get（历史调用方依赖 Optional 返回）。"""
        return self.get(category, name)

    def require(self, category: str, name: str) -> Any:
        """硬查询：找不到 raise RegistryKeyError。"""
        impl = self.get(category, name)
        if impl is None:
            raise RegistryKeyError(name, category, self.list(category))
        return impl

    def list(self, category: str) -> _StrList:
        return list(self._registries.get(category, {}).keys())

    def list_categories(self) -> _StrList:
        return sorted(self._registries.keys())

    def get_registry(self, category: str) -> dict[str, Any]:
        return self._registries.get(category, {})


_global_registry = ComponentRegistry()
_defaults_registered = False


def get_global_registry() -> ComponentRegistry:
    return _global_registry


def defaults_registered() -> bool:
    return _defaults_registered


def mark_defaults_registered() -> None:
    global _defaults_registered
    _defaults_registered = True
