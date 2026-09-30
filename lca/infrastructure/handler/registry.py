"""处理器注册表的共享基础设施。

三个处理器接缝（Action、Effect、Delta）都以 operation 为键发现一个可替换
实现。该基础设施把输入校验、唯一所有权、稳定快照集中在一个深模块中；接缝
定义仍只提供空容器，默认集合仍由各自的 Provider 注册。
"""

from __future__ import annotations

import types
from typing import Generic, TypeVar, cast

_HandlerT = TypeVar("_HandlerT")
_TProtocol = TypeVar("_TProtocol")


class UniqueOperationRegistry(Generic[_HandlerT]):
    """以 operation 为键管理唯一所有者的中性注册表。

    Profile 决定启用或替换哪个 Provider；同一已启动组合内的第二个 Provider
    不得以注册顺序静默覆盖第一个所有者。这样冲突会在接缝处失败，而不是在
    后续运行时表现为隐式行为变化。
    """

    def __init__(self, registry_kind: str) -> None:
        self._registry_kind = registry_kind
        self._handlers: dict[str, _HandlerT] = {}

    def _register(self, operation: str, handler: _HandlerT) -> None:
        """注册一个 operation-local handler，拒绝无效或重复所有者。"""
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError(f"{self._registry_kind}: operation must be a non-empty string")
        if operation in self._handlers:
            raise KeyError(f"{self._registry_kind}: operation {operation!r} already registered")
        self._handlers[operation] = handler

    def _resolve(self, operation: str) -> _HandlerT | None:
        """返回 operation 对应的 handler；未注册时返回 ``None``。"""
        return self._handlers.get(operation)

    def _registered_operations(self) -> tuple[str, ...]:
        """按字典序返回稳定的 operation 发现快照。"""
        return tuple(sorted(self._handlers))


class GenericInMemoryRegistry(UniqueOperationRegistry[_HandlerT], Generic[_HandlerT, _TProtocol]):
    """满足 operation 键控 handler Protocol 的内存注册表。

    Action/Effect/Delta 接缝共享同一容器语义：operation 唯一所有权、按需解析、
    稳定快照。``register``/``resolve`` 在这里实现一次；
    :func:`make_inmemory_registry` 为每个接缝安装 Protocol 声明的快照访问器，
    使各接缝保留自己的词汇表。
    """

    def __init__(self, registry_kind: str) -> None:
        super().__init__(registry_kind)

    def register(self, operation: str, handler: _HandlerT) -> None:
        """注册 ``operation`` 的唯一 handler 所有者。"""
        self._register(operation, handler)

    def resolve(self, operation: str) -> _HandlerT | None:
        """解析 ``operation`` 对应的 handler；未注册返回 ``None``。"""
        return self._resolve(operation)


def make_inmemory_registry(
    kind: str,
    protocol: type[object],
) -> type[GenericInMemoryRegistry[object, object]]:
    """返回满足 ``protocol`` 的内存注册表类（构造器）。

    ``protocol`` 必须是 operation 键控的 handler 注册表 Protocol：除
    ``register``/``resolve`` 外恰好声明一个稳定快照访问器（如 ``registered``、
    ``registered_effect_operations``、``registered_delta_operations``）。
    返回的类以 ``InMemory<Protocol 名>`` 命名，并保持 Provider 的公开构造器
    形态，实例结构上满足 ``protocol``。
    """
    snapshot_method = _snapshot_method_name(protocol)

    def _snapshot(self: GenericInMemoryRegistry[_HandlerT, _TProtocol]) -> tuple[str, ...]:
        return self._registered_operations()

    _snapshot.__name__ = snapshot_method
    _snapshot.__qualname__ = f"InMemory{protocol.__name__}.{snapshot_method}"

    def _init(self: GenericInMemoryRegistry[_HandlerT, _TProtocol]) -> None:
        GenericInMemoryRegistry.__init__(self, kind)

    namespace = {
        snapshot_method: _snapshot,
        "__init__": _init,
        "__module__": __name__,
    }
    return cast(
        "type[GenericInMemoryRegistry[object, object]]",
        types.new_class(
            f"InMemory{protocol.__name__}",
            (GenericInMemoryRegistry[object, object], protocol),
            {},
            lambda ns: ns.update(namespace),
        ),
    )


def _snapshot_method_name(protocol: type[object]) -> str:
    """返回 Protocol 声明的稳定快照访问器名。

    每个 handler 注册表 Protocol 在 ``register``/``resolve`` 之外恰好声明一个
    快照访问器。``dir`` 会混入 ``type`` 的元方法（如 ``mro``），因此只从
    Protocol 自身的 ``__dict__`` 推导。
    """
    candidates = [
        name
        for name in protocol.__dict__
        if not name.startswith("_")
        and name not in {"register", "resolve"}
        and callable(getattr(protocol, name, None))
    ]
    if len(candidates) != 1:
        raise TypeError(
            f"{protocol.__name__} must declare exactly one snapshot accessor besides "
            f"register/resolve; found {sorted(candidates)!r}"
        )
    return candidates[0]


__all__ = [
    "GenericInMemoryRegistry",
    "UniqueOperationRegistry",
    "make_inmemory_registry",
]
