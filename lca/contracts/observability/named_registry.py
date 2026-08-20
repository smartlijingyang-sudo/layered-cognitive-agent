"""NamedRegistry —— 适配 AuditedPluginContext.register() 的通用命名容器。

cordis 的 ``ctx.register(seam, name, value)`` 要求 seam 持有的对象实现
``register(name, value, **kwargs)`` 方法；Python 原生 dict / list 不满足。

本类包装 dict 并暴露同名 ``register``，让 plugin 在 Manifest 校验通过的前提下，
直接调 ``ctx.register("seam", "name", value)`` 注入。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

T = TypeVar("T")


class NamedRegistry(Generic[T]):
    """按 name 索引的可变注册容器。"""

    def __init__(self, initial: dict[str, T] | None = None) -> None:
        self._data: dict[str, T] = dict(initial) if initial else {}

    def register(self, name: str, value: T, **_kwargs: Any) -> None:
        self._data[name] = value

    def get(self, name: str, default: T | None = None) -> T | None:
        return self._data.get(name, default)

    def all(self) -> dict[str, T]:
        return dict(self._data)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, name: object) -> bool:
        return name in self._data
