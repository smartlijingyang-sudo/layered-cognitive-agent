"""事件 v2 console projector —— 试点消费者（ADR-0179 P2）。

订阅全量 category（试点期）；对 ``TEAM_DELEGATION`` 事件按字段渲染一行。
当前仅覆盖 ``DelegationCacheHit``；其余 category 静默忽略（不渲染）。

试点通过后，此消费者会与 ``ConsoleJournalProjector``（旧）并跑一段时间；
最终旧 projector 由本消费者替换（PR-25）。
"""

from __future__ import annotations

import sys
from typing import TextIO

from lca.contracts.event_v2 import (
    Event,
    EventCategory,
    EventRef,
)
from lca.contracts.event_v2 import (
    EventConsumerProtocol as EventConsumer,
)


class ConsoleProjectorConsumer(EventConsumer):
    """控制台投影消费者（试点版）。"""

    _ALL: frozenset[EventCategory] = frozenset(EventCategory)

    def __init__(self, *, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    @property
    def categories(self) -> frozenset[EventCategory]:
        return self._ALL

    def on_event(self, event: Event, ref: EventRef) -> None:
        line = self._render(event)
        if not line:
            return
        print(line, file=self._stream, flush=True)

    def _render(self, event: Event) -> str:
        if event.category is not EventCategory.TEAM_DELEGATION:
            return ""
        # payload 是 pydantic BaseModel；按字段取值，不再读 dict["__type__"]。
        callee_role = getattr(event.payload, "callee_role", "?")
        return f"⇢ {callee_role}: 幂等短路（v2 消费者）"


__all__ = ["ConsoleProjectorConsumer"]
