"""进程级运行事件观察入口(ADR-0065 L9 / PR-5 gateway-exempt)。

进程日志是多个 run 的实时投影,不是新的事件账本。它保留每条 ``StampedEvent``
的原始 ``seq``;跨 run 的唯一性由 ``trace_id`` 与 ``run_id`` 共同提供,绝不
为传输便利改写领域账本的提交顺序。

注意:本模块中 ``LiveTail()`` 是文件级豁免(check_gateway_no_direct_journal_new.py
认为这是 factory 路径);真实 gateway 入口改走 ``gateway.runs._journal_factory``。
"""

from __future__ import annotations

from gateway.runs.live import LiveTail  # ADR-0065 PR-5 gateway-exempt: factory path
from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.protocols import JournalProjector


class ProcessJournal:
    """长生命周期的跨 run 实时投影。"""

    def __init__(self) -> None:
        self.tail = LiveTail()  # ADR-0065 PR-5 gateway-exempt: factory path

    def bind(self) -> JournalProjector:
        return _BoundProcessJournal(self)

    def publish(self, stamped: StampedEvent) -> None:
        """转发已提交事件，不得修改其原始身份或序列。"""
        self.tail.on_event(stamped)


class _BoundProcessJournal(JournalProjector):
    """run 结束时不关闭共享实时投影的轻量适配器。"""

    def __init__(self, owner: ProcessJournal) -> None:
        self._owner = owner

    def on_event(self, stamped: StampedEvent) -> None:
        self._owner.publish(stamped)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None
