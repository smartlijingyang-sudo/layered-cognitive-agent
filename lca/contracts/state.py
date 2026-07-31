"""AgentState and budget control contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from lca.contracts.enums import SnapshotReason
from lca.contracts.ids import new_id
from lca.contracts.lifecycle import TaskStatus
from lca.contracts.member_status import MemberStatus
from lca.contracts.types import Turn


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Budget:
    """Resource budget: steps / tokens / cost / wall-clock."""

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
        """True when step or wall-clock limits are exceeded."""
        if self.max_steps is not None and self.used_steps > self.max_steps:
            return True
        if self.max_wall_clock_seconds is not None:
            elapsed = (_now() - self.started_at).total_seconds()
            if elapsed > self.max_wall_clock_seconds:
                return True
        return False


@dataclass
class StateSnapshot:
    """Checkpoint reference for resume."""

    snapshot_id: str
    step: int
    state_ref: str
    reason: SnapshotReason = SnapshotReason.PERIODIC
    created_at: datetime = field(default_factory=_now)


@dataclass
class AgentState:
    """Full state for one agent cognitive loop."""

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
    from_role: str = ""
    member_status: MemberStatus | None = None
    history: list[Turn] = field(default_factory=list)
    final_output: Any | None = None
    last_error: str | None = None
    active_template: str | None = None

    @property
    def delegated_by(self) -> str:
        import warnings

        warnings.warn(
            "'delegated_by' is deprecated, use 'from_role'",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.from_role

    @delegated_by.setter
    def delegated_by(self, value: str) -> None:
        self.from_role = value

    def snapshot(self, reason: SnapshotReason = SnapshotReason.PERIODIC) -> StateSnapshot:
        """Append a checkpoint and return its reference."""
        snap = StateSnapshot(
            snapshot_id=new_id("snap"),
            step=self.step,
            state_ref=f"mem://{self.trace_id}/{self.step}",
            reason=reason,
        )
        self.checkpoints.append(snap)
        return snap
