"""Run State Reducer —— 纯函数推导 run 终态（ADR-0055 不变量 N3）。

状态是事件流的纯函数，不存在独立的 mutable state。
fold_run_state(events) 是唯一的终态推导路径——消灭双 owner 漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.models.observability.event.event import RuntimeKind
from lca.contracts.models.observability.journal.journal import (
    AgentRunFinished,
    RuntimeObserved,
    StampedEvent,
    TeamRunFinished,
)
from lca.contracts.observability.registry.status import RunLifecycleStatus

_CARRIER_TERMINAL_OPERATION = "run.lifecycle.failed"

# COMPAT(delete-when: rg "\bRunStatus\." 生产引用归零、全部改走 RunLifecycleStatus,
# tracking: ADR-0183 PR-11)
RunStatus = RunLifecycleStatus


@dataclass(frozen=True)
class RunState:
    """Run 的派生状态——纯函数 fold(events) 的结果。"""

    status: RunLifecycleStatus
    finished_at: float | None = None
    error: str | None = None


def fold_run_state(events: Sequence[StampedEvent]) -> RunState:
    """从事件流推导 run 终态。纯函数，无 I/O。

    规则：按时间戳取最后一条根 run 终态事实（TeamRunFinished、
    AgentRunFinished、carrier ``RuntimeObserved(run.lifecycle.failed)``）。
    无终态事实 → running。
    """
    last: RunState | None = None
    last_ts: float | None = None

    for stamped in events:
        if stamped.scope.parent_run_id is not None:
            continue
        event = stamped.event
        candidate: RunState | None = None
        if isinstance(event, (TeamRunFinished, AgentRunFinished)):
            candidate = RunState(
                status=RunLifecycleStatus.from_finish_status(event.status),
                finished_at=stamped.ts,
                error=event.error or None,
            )
        elif isinstance(event, RuntimeObserved) and _is_carrier_terminal_observed(event):
            candidate = RunState(
                status=RunLifecycleStatus.FAILED,
                finished_at=stamped.ts,
                error=event.error_message or None,
            )
        if candidate is not None and (last_ts is None or stamped.ts >= last_ts):
            last = candidate
            last_ts = stamped.ts

    return last if last is not None else RunState(status=RunLifecycleStatus.RUNNING)


def _is_carrier_terminal_observed(event: RuntimeObserved) -> bool:
    return (
        event.operation == _CARRIER_TERMINAL_OPERATION
        and event.kind is RuntimeKind.ERROR
    )


__all__ = ["RunState", "RunStatus", "fold_run_state"]
