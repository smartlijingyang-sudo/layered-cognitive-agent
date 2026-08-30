"""AgentState and budget control contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.enums import SnapshotReason
from lca.contracts.atoms.ids import RunId, TraceId, new_id, utc_now
from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.decision import Turn
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.team.team_awareness import TeamAwareness

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor


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
    started_at: datetime = field(default_factory=utc_now)

    def exceeded(self, resource: str | None = None) -> bool:
        """Return whether a configured hard limit has been reached.

        ``resource`` accepts the portable loop-guard names ``steps``,
        ``tokens``, ``cost_usd`` and ``wall_clock_seconds``. Omitting it
        preserves the runtime-wide check used by the State-cluster StopPolicy. This method
        reports an overage; loop re-entry uses its own stricter admission
        policy so the current terminal phase remains able to close cleanly.
        """
        checks = {
            "steps": _budget_limit_exceeded(self.used_steps, self.max_steps),
            "tokens": _budget_limit_exceeded(self.used_tokens, self.max_tokens),
            "cost_usd": _budget_limit_exceeded(self.used_cost_usd, self.max_cost_usd),
            "wall_clock_seconds": _wall_clock_exceeded(self),
        }
        if resource is not None:
            try:
                return checks[resource]
            except KeyError as exc:
                raise ValueError(f"unknown budget resource: {resource}") from exc
        return any(checks.values())


def _budget_limit_exceeded(used: int | float, maximum: int | float | None) -> bool:
    """Return whether one numeric resource has exceeded its configured maximum."""

    return maximum is not None and used > maximum


def _wall_clock_exceeded(budget: Budget) -> bool:
    """Return whether the budget's elapsed wall-clock has exceeded its maximum."""

    if budget.max_wall_clock_seconds is None:
        return False
    elapsed = (utc_now() - budget.started_at).total_seconds()
    return bool(elapsed > budget.max_wall_clock_seconds)


@dataclass
class StateSnapshot:
    """Checkpoint reference for resume."""

    snapshot_id: str
    step: int
    state_ref: str
    reason: SnapshotReason = SnapshotReason.PERIODIC
    created_at: datetime = field(default_factory=utc_now)
    phase_cursor: PhaseRunCursor | None = field(default=None, compare=True, repr=True)
    # The trace remains stable across a paused turn and its eventual resume.
    # ``run_id`` is filled by the Agent lifecycle boundary after it owns the
    # enclosing RunScope; state creation deliberately remains runtime-agnostic.
    trace_id: TraceId = ""  # type: ignore[assignment]
    run_id: RunId = ""  # type: ignore[assignment]


@dataclass
class AgentState:
    """Full state for one agent cognitive loop.

    Generic loop fields only. The lead's live team cognition lives under the
    optional ``team_awareness`` slot — single slot, single type (ADR-0035).
    """

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
    team_awareness: TeamAwareness | None = None
    history: list[Turn] = field(default_factory=list)
    final_output: Any | None = None
    last_error: str | None = None
    active_template: str | None = None
    activated_skills: list[ActivatedSkill] = field(default_factory=list)

    def snapshot(self, reason: SnapshotReason = SnapshotReason.PERIODIC) -> StateSnapshot:
        """Append a checkpoint and return its reference."""
        snap = StateSnapshot(
            snapshot_id=new_id("snap"),
            step=self.step,
            state_ref=f"mem://{self.trace_id}/{self.step}",
            reason=reason,
            trace_id=TraceId(self.trace_id),
        )
        self.checkpoints.append(snap)
        return snap
