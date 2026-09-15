"""TaskList / TaskEntry — typed plan store seam (ADR-0228 §Decision 3).

Cross-graph boundary between ``plan.compose`` / ``plan.revise`` (plan
region) and ``agent.reasoning.turn`` (which reads entries for the next
turn). Two contracts:

- :class:`TaskEntry` is a single objective with stable ``task_id``,
  ``status`` (closed-set literal), dependency list, and monotonic
  ``revision``. Closed boundary — no surprise fields (``extra="forbid"``)
  and no mutation downstream (``frozen=True``).
- :class:`TaskList` is the container emitted by plan nodes; its own
  ``revision`` bumps on every replacement so consumers (Reducer / Brain)
  can tell whether the list changed without deep-equality.

Single-writer: ``AgentState.task_list``. Brain reads; Reducer folds;
plan nodes emit a *new* ``TaskList`` typed port. No node mutates the
container in place.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TaskId(str):
    """Branded task id (str subclass for typing).

    Branded only at the type level; runtime identity is ``str``. Stable
    across revisions — once issued, the same id is reused across
    :class:`TaskList` revisions to identify the same objective.
    """


TaskStatus = Literal["pending", "in_progress", "blocked", "completed", "skipped"]
"""Closed-set entry lifecycle states. New states require ADR (AGENTS.md §3 C11)."""


class TaskEntry(BaseModel):
    """One objective within a :class:`TaskList`."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    task_id: TaskId
    objective: str
    status: TaskStatus = "pending"
    depends_on: tuple[TaskId, ...] = ()
    revision: int = 0
    created_at_turn: int
    completed_at_turn: int | None = None


class TaskList(BaseModel):
    """Typed plan store; emitted by ``plan.compose`` / ``plan.revise``.

    ``revision`` bumps on every replacement (never decremented). Consumers
    that cache a derived view use this as the cheap invalidation token.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    entries: tuple[TaskEntry, ...] = ()
    revision: int = 0


class Reflection(BaseModel):
    """Reflect → plan bridge: replan signal + blocked-task ids + rationale.

    Owned by the reflect phase; consumed by ``plan.revise`` (PR-3.7.b
    sibling node). Lives in this module because it shares the
    :class:`TaskId` brand and the closed-boundary discipline
    (``frozen=True`` + ``extra="forbid"``). NOT the ``Reflection`` in
    :mod:`lca.contracts.models.core.execution.decision` — that one is
    the legacy critic-output DTO; this one is the reflect→plan bridge
    added by ADR-0228 §Decision 3 (plan.revise wiring).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    replan_requested: bool = False
    blocked_tasks: tuple[TaskId, ...] = ()
    rationale: str = ""


__all__ = ["Reflection", "TaskEntry", "TaskId", "TaskList", "TaskStatus"]
