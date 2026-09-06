"""处理器注册表的共享基础设施。

三个处理器接缝（Action、Effect、Delta）都以 operation 为键发现一个可替换
实现。该基础设施把输入校验、唯一所有权、稳定快照集中在一个深模块中；接缝
定义仍只提供空容器，默认集合仍由各自的 Provider 注册。
"""

from __future__ import annotations

from typing import Generic, TypeVar

_HandlerT = TypeVar("_HandlerT")


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


__all__ = ["UniqueOperationRegistry"]
