"""Journal sink —— 事件机制默认 sink（ADR-0180 D4）。

业务方不直接调 journal.write；sink 负责 EventRecord 缓存。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from lca.contracts.atoms.ids import new_id
from lca.contracts.event import EventPayload
from lca_kernel.events.mechanism import EventRef


@dataclass(frozen=True, slots=True)
class EventRecord:
    """sink 写盘后的引用。"""

    event_id: str
    category: str
    ts: float


class JournalSink:
    """事件机制默认 sink（plugin 形式）。"""

    def __init__(self) -> None:
        self._records: list[EventRecord] = []

    def on_event(self, payload: EventPayload, ref: EventRef) -> None:
        record = EventRecord(
            event_id=new_id("evt"),
            category=ref.category,
            ts=time.time(),
        )
        self._records.append(record)

    @property
    def records(self) -> tuple[EventRecord, ...]:
        return tuple(self._records)


__all__ = ["EventRecord", "JournalSink"]
