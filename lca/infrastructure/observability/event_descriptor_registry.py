"""InMemoryEventDescriptorRegistry —— 进程内注册中心实现。

线程不安全：cordis 的 ``setup()`` 顺序发生在主线程，boot 期使用足够。
事件 append 是单写者（RunStore 串行化），读侧（投影器、Inspector）允许
任意并发。读路径只读 ``self._by_name`` 的不可变快照。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry

if TYPE_CHECKING:
    from lca.contracts.models.observability.event import EventDescriptor
    from lca.contracts.models.observability.journal import JournalEvent


class DuplicateEventDescriptorError(ValueError):
    """同名描述符已存在且 ``replace=False``。"""


class UnknownEventDescriptorError(KeyError):
    """未登记事件的类型名查询失败。"""


class InMemoryEventDescriptorRegistry(EventDescriptorRegistry):
    """线程不安全的进程内注册中心；boot 期一次性 bootstrap，运行时仅追加。"""

    def __init__(self, initial: Iterable[EventDescriptor] = ()) -> None:
        self._by_name: dict[str, EventDescriptor] = {}
        for descriptor in initial:
            self.register(descriptor)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.all())

    def __len__(self) -> int:
        return len(self._by_name)

    def get(self, type_name: str) -> EventDescriptor | None:
        return self._by_name.get(type_name)

    def require(self, type_name: str) -> EventDescriptor:
        descriptor = self._by_name.get(type_name)
        if descriptor is None:
            raise UnknownEventDescriptorError(f"未登记事件描述符：{type_name!r}")
        return descriptor

    def all(self) -> Iterable[EventDescriptor]:
        return tuple(self._by_name.values())

    def all_type_names(self) -> Iterable[str]:
        return tuple(self._by_name.keys())

    def register(self, descriptor: EventDescriptor, *, replace: bool = False) -> None:
        existing = self._by_name.get(descriptor.type_name)
        if existing is not None and not replace:
            raise DuplicateEventDescriptorError(
                f"事件描述符 {descriptor.type_name!r} 已登记；显式 replace=True 才覆盖"
            )
        self._by_name[descriptor.type_name] = descriptor

    def payload_class_for(self, event: JournalEvent | str) -> type[JournalEvent] | None:
        type_name = event if isinstance(event, str) else type(event).__name__
        descriptor = self._by_name.get(type_name)
        return descriptor.payload_class if descriptor is not None else None


__all__ = [
    "DuplicateEventDescriptorError",
    "InMemoryEventDescriptorRegistry",
    "UnknownEventDescriptorError",
]
