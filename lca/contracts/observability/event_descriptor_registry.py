"""EventDescriptor 注册中心（ADR-0063 PR-7 source inversion）。

事件描述符的单一源（type_name / plane / domain / emitter / durability /
audience / sensitivity / retention / otel_kind / payload_class）。

旧 ``JOURNAL_CATALOG`` + ``JOURNAL_CATALOG_META`` 双表已被本注册中心取代；
消费者（投影器、SSE 帧选择器、OTel 映射器、TraceInspector）只读不写。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lca.contracts.models.observability.event import EventDescriptor
    from lca.contracts.models.observability.journal import JournalEvent


@runtime_checkable
class EventDescriptorRegistry(Protocol):
    """事件描述符注册中心：插件可在运行时登记新事件或扩展元数据。"""

    def get(self, type_name: str) -> "EventDescriptor | None":
        """按类型名查询；未登记返回 None。"""

    def require(self, type_name: str) -> "EventDescriptor":
        """按类型名查询；未登记抛 ``KeyError``。"""

    def all(self) -> Iterable["EventDescriptor"]:
        """全部已登记描述符的稳定迭代。"""

    def all_type_names(self) -> Iterable[str]:
        """全部已登记类型名（与 ``JOURNAL_EVENT_CLASSES`` 对齐的快照）。"""

    def register(self, descriptor: "EventDescriptor", *, replace: bool = False) -> None:
        """登记描述符；``replace=False`` 时若同名已存在抛 ``ValueError``。"""

    def payload_class_for(self, event: "JournalEvent | str") -> type["JournalEvent"] | None:
        """按事件实例或类型名查询 payload 类；用于反序列化绑定。"""