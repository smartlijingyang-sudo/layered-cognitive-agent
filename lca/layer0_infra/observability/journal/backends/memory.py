"""进程内 InMemoryJournalStore —— ``JournalStoreBackend`` 唯一当前实现。

线程不安全：cordis 的 ``setup()`` 顺序发生在主线程，boot 期使用足够。
事件 append 是单写者（``RunStore.append`` 串行化），读侧（投影器、Inspector）允许
任意并发。读路径只读 ``self._events`` 的不可变 tuple 副本。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.models.observability.journal import StampedEvent


class InMemoryJournalStore:
    """append-only 内存账本；list 持有 + tuple snapshot 暴露。"""

    def __init__(self) -> None:
        self._events: list["StampedEvent"] = []

    def append(self, stamped: "StampedEvent") -> "StampedEvent":
        self._events.append(stamped)
        return stamped

    def events(self) -> Sequence["StampedEvent"]:
        return tuple(self._events)

    def get(self, seq: int) -> "StampedEvent | None":
        if seq < 1 or seq > len(self._events):
            return None
        return self._events[seq - 1]

    def read_from(self, after_seq: int) -> Sequence["StampedEvent"]:
        start = max(after_seq, 0)
        return tuple(self._events[start:])

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __len__(self) -> int:
        return len(self._events)