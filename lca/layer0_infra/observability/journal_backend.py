"""MemoryJournal —— 默认 JournalBackend（RunStore + ProjectionRegistry + AttributePolicy）。

业务层 ``record(event)`` → MemoryJournal.write(event)：
1. AttributePolicy 脱敏/截断；
2. RunStore.append 分配 seq、盖 scope、通知 readers；
3. reader 扇出（ConsoleReader/JsonlReader/OtelReader/LangfuseReader）。

scorers 不挂在这里 —— 走独立 ``score()`` 路径，由 facade 解析。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.models.observability.journal import JournalEvent, StampedEvent
from lca.contracts.observability.event_descriptor_registry import EventDescriptorRegistry
from lca.contracts.observability.ports import JournalBackend
from lca.layer0_infra.observability.journal.engine import RunStore

if TYPE_CHECKING:
    from lca.contracts.observability.ports import AttributePolicyBackend
    from lca.contracts.protocols import JournalProjector


class MemoryJournal(JournalBackend):
    """进程内 Journal：RunStore + ProjectionRegistry + 可选 AttributePolicy。"""

    def __init__(
        self,
        *,
        policy: AttributePolicyBackend | None = None,
        projections: tuple[JournalProjector, ...] = (),
        descriptor_registry: EventDescriptorRegistry | None = None,
    ) -> None:
        self._store = RunStore(
            policy=policy,
            projections=projections,
            descriptor_registry=descriptor_registry,
        )

    @property
    def store(self) -> RunStore:
        """暴露 RunStore 给需要直接 append 的低层代码。"""
        return self._store

    def with_projection(self, projection: JournalProjector) -> MemoryJournal:
        """返回追加 ``projection`` 后的新 MemoryJournal（原实例不变）。"""
        return MemoryJournal(
            policy=self._store.policy,
            projections=(*self._store.projections, projection),
        )

    def write(self, event: JournalEvent) -> StampedEvent | None:
        return self._store.append(event)

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.close()


__all__ = ["MemoryJournal"]
