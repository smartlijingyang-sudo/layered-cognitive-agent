"""第5.2节：State 与预算控制契约。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class Budget:
    max_tokens: Optional[int] = None
    max_cost_usd: Optional[float] = None
    max_steps: Optional[int] = None
    max_wall_clock_seconds: Optional[int] = None
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
    status: Literal["running", "paused", "waiting_human", "completed", "failed"] = "running"
    extra: dict[str, Any] = field(default_factory=dict)

    def snapshot(self, reason: str = "periodic") -> StateSnapshot:
        snap = StateSnapshot(
            snapshot_id=_new_id("snap"),
            step=self.step,
            state_ref=f"mem://{self.trace_id}/{self.step}",
            reason=reason,  # type: ignore[arg-type]
        )
        self.checkpoints.append(snap)
        return snap
