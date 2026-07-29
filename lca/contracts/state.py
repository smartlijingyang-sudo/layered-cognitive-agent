"""第5.2节：State 与预算控制契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from lca.contracts.delegation_context import _delegator as _current_delegator  # noqa: F401

# 过渡期 re-export，见 ADR-0017；新代码请直接 import lca.contracts.delegation_context
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.team_progress import DelegationLedgerProtocol
from lca.contracts.types import Turn


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Budget:
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_steps: int | None = None
    max_wall_clock_seconds: int | None = None
    used_tokens: int = 0
    used_cost_usd: float = 0.0
    used_steps: int = 0
    started_at: datetime = field(default_factory=_now)
    extra: dict[str, Any] = field(default_factory=dict)

    def exceeded(self) -> bool:
        if self.max_steps is not None and self.used_steps > self.max_steps:
            return True
        if self.max_wall_clock_seconds is not None:
            elapsed = (_now() - self.started_at).total_seconds()
            if elapsed > self.max_wall_clock_seconds:
                return True
        return False


@dataclass
class StateSnapshot:
    snapshot_id: str
    step: int
    state_ref: str
    reason: Literal["periodic", "pre_approval", "manual", "on_error"]
    created_at: datetime = field(default_factory=_now)


@dataclass
class TypedState:
    trace_id: str
    task: str
    budget: Budget
    schema_version: str = "1.0"
    working_memory: dict[str, Any] = field(default_factory=dict)
    retrieved_context: list[Any] = field(default_factory=list)
    step: int = 0
    checkpoints: list[StateSnapshot] = field(default_factory=list)
    status: TaskStatus = TaskStatus.WORKING
    extra: dict[str, Any] = field(default_factory=dict)
    agent_role: str = ""
    delegated_by: str = ""
    team_progress: DelegationLedgerProtocol | None = None
    # 认知闭环历史：每步 Turn(decision, observation, reflection)
    history: list[Turn] = field(default_factory=list)
    # ── 框架运行槽位（一等字段，禁止再走 working_memory 裸字符串）──
    final_output: Any | None = None
    last_error: str | None = None
    active_template: str | None = None
    team_progress_text: str | None = None

    def snapshot(self, reason: str = "periodic") -> StateSnapshot:
        snap = StateSnapshot(
            snapshot_id=new_id("snap"),
            step=self.step,
            state_ref=f"mem://{self.trace_id}/{self.step}",
            reason=reason,  # type: ignore[arg-type]
        )
        self.checkpoints.append(snap)
        return snap
