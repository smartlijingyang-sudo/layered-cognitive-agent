"""执行日志投影协议 —— journal 的视图消费契约（ADR-0037）。

Journal-as-Truth：日志是唯一真相，视图是投影。新增后端 = 新增投影器
（OTel/console/jsonl/序列图/...），契约不变。投影器必须只读、幂等、
故障隔离（单投影器异常不得中断 run——由引擎包装保证）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.journal import StampedEvent


@runtime_checkable
class JournalProjector(Protocol):
    """journal 事件的投影器：消费盖章记录，产出视图。

    - ``on_event``：按 seq 顺序投递；投影器内部异常由引擎隔离；
    - ``flush`` / ``close``：生命周期与 hub 对齐（flush 可多次调用）。
    """

    def on_event(self, stamped: StampedEvent) -> None:
        """消费一条盖章日志记录（含关联骨架）。"""
        ...

    def flush(self) -> None:
        """把缓冲的投影刷到底层介质。"""
        ...

    def close(self) -> None:
        """释放资源（close 后 on_event 行为未定义）。"""
        ...
