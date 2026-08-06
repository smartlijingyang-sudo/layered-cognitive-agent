"""注册表基础设施 —— NamedRegistry 泛型基类 + ComponentRegistry 组合器。

语义约定：
- ``get``：软查询，找不到返回 None
- ``require`` / ``NamedRegistry.resolve``：硬查询，找不到 raise RegistryKeyError

ComponentRegistry 是「category → NamedRegistry」的组合器：每个 category
持有一个 NamedRegistry 实例（错误消息以 category 为种类名），注册与查询
全部委派给 NamedRegistry，不保留平行的查找实现。

本模块不再持有进程级全局单例。ComponentRegistry / NamedRegistry
的实例生命周期由调用方决定 —— 框架默认路径中，实例归 TeamComposer 私有持有
（见 lca.contracts.mechanisms.registries.Registries、lca.layer4_app.composer.TeamComposer）。
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

    种类名（用于错误消息）有两种声明方式：
    - 子类通过 ``_REGISTRY_KIND`` 类属性声明；
    - 构造时传 ``kind`` 参数按实例覆盖（ComponentRegistry 组合用法）。

    可选择覆盖 ``resolve()`` 以改变解析语义（如工厂调用、类型转换）。
    """

    _REGISTRY_KIND: str = "条目"

    def __init__(self, kind: str | None = None) -> None:
        if kind is not None:
            self._REGISTRY_KIND = kind
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

    组合实现：每个 category 对应一个 ``NamedRegistry(kind=category)``，
    本类只负责 category 维度的路由，查询语义与 NamedRegistry 一致。
    查询接口（get / require / list）不会为未知 category 创建空注册表。

    category 例如 "observability"、"memory"、"state_store" 等；
    name 是用户可见的实现名称，例如 "console"、"simple" 等。
    值可以是类（无参构造）或工厂函数（接受上下文参数）。

    运行时绑定型注册表（Action / Tool / Transport）应由 TeamComposer 注入实例，
    不要用 ComponentRegistry 承载。
    """

    def __init__(self) -> None:
        self._registries: dict[str, NamedRegistry[Any]] = {}

    def _named(self, category: str) -> NamedRegistry[Any]:
        registry = self._registries.get(category)
        if registry is None:
            registry = NamedRegistry[Any](kind=category)
            self._registries[category] = registry
        return registry

    def register(self, category: str, name: str, impl: Any) -> None:
        self._named(category).register(name, impl)

    def get(self, category: str, name: str) -> Any | None:
        """软查询：找不到返回 None。"""
        registry = self._registries.get(category)
        return registry.get(name) if registry is not None else None

    def require(self, category: str, name: str) -> Any:
        """硬查询：找不到 raise RegistryKeyError（种类名为 category）。"""
        registry = self._registries.get(category)
        impl = registry.get(name) if registry is not None else None
        if impl is None:
            raise RegistryKeyError(name, category, self.list(category))
        return impl

    def list(self, category: str) -> _StrList:
        registry = self._registries.get(category)
        return registry.list() if registry is not None else []

    def list_categories(self) -> _StrList:
        return sorted(self._registries.keys())
