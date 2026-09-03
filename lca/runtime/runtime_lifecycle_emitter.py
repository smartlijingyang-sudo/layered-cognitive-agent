"""Project runtime state and terminal results into lifecycle boundary events.

This module owns the protocol adaptation between the declarative runtime and
passive lifecycle subscribers. ``CognitiveRuntime`` remains responsible only
for fresh/resume orchestration and delegates event construction here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
)
from lca.runtime.runtime_bindings import DeclarativeRuntimeBindings

if TYPE_CHECKING:
    from lca.infrastructure.observability.spine.event_record import Outcome


class RuntimeLifecycleEmitter:
    """Own the lifecycle event seam for one verified runtime binding."""

    def __init__(self, bindings: DeclarativeRuntimeBindings) -> None:
        self._bindings = bindings

    async def publish_terminal(self, state: object, result: Result) -> None:
        """Project a terminal carrier result into one passive lifecycle event."""
        await self.publish(
            _event_type_for_result(result),
            state,
            status=result.status,
            state_ref=result.final_state_ref,
            phase_cursor=_phase_cursor_from_result(result),
            journal_sequence=_journal_sequence_from_result(result),
            trace_id=result.trace_id,
        )

    async def publish(
        self,
        event_type: RuntimeLifecycleEventType,
        state: object,
        *,
        status: TaskStatus | None = None,
        state_ref: str | None = None,
        phase_cursor: str | None = None,
        journal_sequence: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Publish one immutable event without exposing live runtime state."""
        budget = getattr(state, "budget", None)
        resolved_status = status or getattr(state, "status", TaskStatus.WORKING)
        if not isinstance(resolved_status, TaskStatus):
            resolved_status = TaskStatus.WORKING
        event = RuntimeLifecycleEvent(
            type=event_type,
            trace_id=trace_id or str(getattr(state, "trace_id", "")),
            plan_ref=self._bindings.plan_ref(),
            status=resolved_status,
            step=int(getattr(state, "step", 0)),
            budget=RuntimeBudgetSnapshot(
                max_tokens=getattr(budget, "max_tokens", None),
                max_cost_usd=getattr(budget, "max_cost_usd", None),
                max_steps=getattr(budget, "max_steps", None),
                max_wall_clock_seconds=getattr(budget, "max_wall_clock_seconds", None),
                used_tokens=getattr(budget, "used_tokens", 0),
                used_cost_usd=getattr(budget, "used_cost_usd", 0.0),
                used_steps=getattr(budget, "used_steps", 0),
            ),
            state_ref=state_ref,
            phase_cursor=phase_cursor,
            journal_sequence=journal_sequence,
        )
        # PR-3.4: emit runtime.event_publisher.publish before forwarding to
        # the legacy lifecycle subscriber chain. The helper is a silent
        # no-op when no spine is wired (default in unit tests), so the
        # existing DI seam to the legacy RuntimeLifecyclePublisher is
        # preserved untouched.
        from lca.plugins.events.publishers.spine_reflector_runtime import (
            emit_runtime_event_publisher_publish,
        )

        resolved_trace_id = trace_id or str(getattr(state, "trace_id", ""))
        outcome: Outcome = "success"
        try:
            await self._bindings.lifecycle_publisher.publish(event)
        except BaseException:
            outcome = "failure"
            raise
        finally:
            emit_runtime_event_publisher_publish(
                event_type=event_type.value,
                trace_id=resolved_trace_id,
                outcome=outcome,
            )


def _event_type_for_result(result: Result) -> RuntimeLifecycleEventType:
    """Map terminal status into the lifecycle event closure."""
    if result.status is TaskStatus.INPUT_REQUIRED:
        return RuntimeLifecycleEventType.INPUT_REQUIRED
    if result.status is TaskStatus.CANCELED:
        return RuntimeLifecycleEventType.CANCELED
    if result.status is TaskStatus.PARTIAL:
        return RuntimeLifecycleEventType.PARTIAL
    if result.status is TaskStatus.COMPLETED:
        return RuntimeLifecycleEventType.COMPLETED
    return RuntimeLifecycleEventType.FAILED


def _phase_cursor_from_result(result: Result) -> str | None:
    """Read only the stable cursor identity exposed by terminal projection."""
    raw = result.extra.get("phase_cursor")
    if isinstance(raw, dict):
        for key in ("node_id", "cursor"):
            value = raw.get(key)
            if isinstance(value, str) and value:
                return value
        return None
    value = getattr(raw, "node_id", None)
    return value if isinstance(value, str) and value else None


def _journal_sequence_from_result(result: Result) -> int | None:
    """Read an optional validated journal sequence from result metadata."""
    value = result.extra.get("journal_seq_end")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


__all__ = [
    "RuntimeLifecycleEmitter",
    "_event_type_for_result",
    "_journal_sequence_from_result",
    "_phase_cursor_from_result",
]
