"""Passive lifecycle-event contracts for declarative Agent Loop executions.

The lifecycle seam intentionally accepts immutable, carrier-safe value objects
only.  Subscribers cannot obtain ``AgentState``, a capability scope, Journal,
Reducer, or Effect Gateway, so progress projection cannot become a control or
state-mutation backchannel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from lca.contracts.models.core.lifecycle import TaskStatus


class RuntimeLifecycleEventType(StrEnum):
    """Closed set of runtime-boundary events emitted for one Agent Loop turn."""

    STARTED = "started"
    RESUMED = "resumed"
    COMPLETED = "completed"
    PARTIAL = "partial"
    INPUT_REQUIRED = "input_required"
    FAILED = "failed"
    CANCELED = "canceled"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"


@dataclass(frozen=True, slots=True)
class RuntimeBudgetSnapshot:
    """Immutable budget counters safe to share with passive lifecycle subscribers."""

    max_tokens: int | None
    max_cost_usd: float | None
    max_steps: int | None
    max_wall_clock_seconds: int | None
    used_tokens: int
    used_cost_usd: float
    used_steps: int


@dataclass(frozen=True, slots=True)
class RuntimeLifecycleEvent:
    """One carrier-safe lifecycle projection for an Agent Loop execution.

    The payload excludes task input, prompts, working memory, artifacts, tool
    arguments, model output, error details, and approval payloads.  Consumers
    may correlate progress through ``trace_id`` / ``plan_ref`` and use durable
    references only through values already standardized by     terminal projection. Phase events additionally expose only the declared node,
    semantic phase, and normalized result kind; they never contain executor payload,
    exception details, state, artifacts, prompts, or tool arguments.
    """

    type: RuntimeLifecycleEventType

    trace_id: str
    plan_ref: str
    status: TaskStatus
    step: int
    budget: RuntimeBudgetSnapshot
    state_ref: str | None = None
    phase_cursor: str | None = None
    journal_sequence: int | None = None
    semantic_phase: str | None = None
    result_kind: str | None = None


@runtime_checkable
class RuntimeLifecycleSubscriber(Protocol):
    """Passively consume an immutable Agent Loop lifecycle event."""

    async def publish(self, event: RuntimeLifecycleEvent) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeLifecycleSubscriberContribution:
    """One independently registered runtime-lifecycle subscriber."""

    id: str
    subscriber: RuntimeLifecycleSubscriber
    priority: int = 100


@runtime_checkable
class RuntimeLifecycleSubscriberRegistry(Protocol):
    """Register subscribers during profile boot and freeze them before execution."""

    def register(self, contribution: RuntimeLifecycleSubscriberContribution) -> None: ...

    def snapshot(self) -> tuple[RuntimeLifecycleSubscriberContribution, ...]: ...


@runtime_checkable
class RuntimeLifecyclePublisher(Protocol):
    """Publish runtime-boundary events without exposing execution control objects."""

    async def publish(self, event: RuntimeLifecycleEvent) -> None: ...


__all__ = [
    "RuntimeBudgetSnapshot",
    "RuntimeLifecycleEvent",
    "RuntimeLifecycleEventType",
    "RuntimeLifecyclePublisher",
    "RuntimeLifecycleSubscriber",
    "RuntimeLifecycleSubscriberContribution",
    "RuntimeLifecycleSubscriberRegistry",
]
