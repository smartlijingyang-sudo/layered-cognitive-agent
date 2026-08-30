"""进程级运行事件实时投影。

``ProcessJournal`` 只是多个 run 共享的实时观察投影，不是新的事实账本：它
保留每条 ``StampedEvent`` 的身份和顺序，并把事件转发给进程级 ``LiveTail``。
它位于 L0，使 Gateway 只消费由 profile 选择的账本工厂，而不再决定实时投影
使用哪种实现。
"""

from __future__ import annotations

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.journal.live_tail import LiveTail


class ProcessJournal:
    """长生命周期的跨 run 实时投影。"""

    def __init__(self) -> None:
        self.tail = LiveTail()

    def bind(self) -> JournalProjector:
        """返回 run-scoped 投影；关闭它不会关闭共享的实时尾流。"""
        return _BoundProcessJournal(self)

    def publish(self, stamped: StampedEvent) -> None:
        """转发已提交事件，不得修改其原始身份或序列。"""
        self.tail.on_event(stamped)


class _BoundProcessJournal(JournalProjector):
    """避免单个 run 的关闭影响进程级实时投影的轻量适配器。"""

    def __init__(self, owner: ProcessJournal) -> None:
        self._owner = owner

    def on_event(self, stamped: StampedEvent) -> None:
        self._owner.publish(stamped)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


__all__ = ["ProcessJournal"]
