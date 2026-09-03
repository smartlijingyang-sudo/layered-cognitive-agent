"""Run State Reducer —— 纯函数推导 run 终态（ADR-0055 不变量 N3）。

状态是事件流的纯函数，不存在独立的 mutable state。
fold_run_state(events) 是唯一的终态推导路径——消灭双 owner 漂移。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    StampedEvent,
    TeamRunFinished,
)
from lca.contracts.observability.status import RunLifecycleStatus

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

    规则（按优先级，从后往前扫描）：
    1. 存在 TeamRunFinished → 其 status 即终态
    2. 存在 AgentRunFinished(status=error) 且 scope.parent_run_id is None → failed
    3. 存在 AgentRunFinished 且 scope.parent_run_id is None → completed
    4. 否则 → running
    """
    last_team_finish: TeamRunFinished | None = None
    last_team_finish_ts: float | None = None
    last_root_agent_finish: AgentRunFinished | None = None
    last_root_agent_finish_ts: float | None = None

    for stamped in events:
        event = stamped.event
        if isinstance(event, TeamRunFinished):
            last_team_finish = event
            last_team_finish_ts = stamped.ts
        elif isinstance(event, AgentRunFinished) and stamped.scope.parent_run_id is None:
            last_root_agent_finish = event
            last_root_agent_finish_ts = stamped.ts

    if last_team_finish is not None:
        return RunState(
            status=RunLifecycleStatus.from_finish_status(last_team_finish.status),
            finished_at=last_team_finish_ts,
            error=last_team_finish.error or None,
        )

    if last_root_agent_finish is not None:
        return RunState(
            status=RunLifecycleStatus.from_finish_status(last_root_agent_finish.status),
            finished_at=last_root_agent_finish_ts,
            error=last_root_agent_finish.error or None,
        )

    return RunState(status=RunLifecycleStatus.RUNNING)
