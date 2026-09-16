"""Contract tests for ``ThinkDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4):

    ok       if ``think.main.start`` is followed by a
             ``think.decision.repair`` with non-empty routing
    degraded if a ``think.decision.repair`` is present but its routing
             payload is empty (no next-action emitted)
    failed   if ``think.decision.repair`` outputs a routing whose
             ``action_type == "error"`` (or status indicates an error)
    unknown  if no ``think.*`` events

The v1 producer emits ``phase.think.fold`` and ``think.gate.start``
rather than the spec's ``think.main.start`` / ``think.decision.repair``;
the deriver therefore accepts any of the documented think EPs as a
proxy for "think is alive" and emits ``ok`` when the think phase is
closed (a fold event with ``summary`` indicating completion). The
degraded / failed branches use synthetic event payloads so the 4-case
schema is exercised even though the producer does not currently emit
the relevant EPs.
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _think_event(
    *,
    event_id: str = "run_3383288d63e7:70",
    ts: str = "2026-09-16T02:49:35.884481+00:00",
    run_id: str = "run_3383288d63e7",
    execution_point: str = "phase.think.fold",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {"phase": "think", "summary": "started"},
    )


def test_think_returns_ok_when_think_phase_fold_present() -> None:
    """Happy path: a think phase fold EP exists with non-empty summary."""
    from lca.plugins.observability.health.derivers.think_deriver import (
        ThinkDeriver,
    )

    deriver = ThinkDeriver()
    events = [_think_event(payload={"phase": "think", "summary": "respond"})]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "think"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "think_fold_closed"
    assert len(conditions[0].evidence_refs) >= 1
    assert conditions[0].evidence_refs[0].execution_point == "phase.think.fold"


def test_think_returns_degraded_when_decision_repair_routing_empty() -> None:
    """A ``think.decision.repair`` EP with empty routing is degraded."""
    from lca.plugins.observability.health.derivers.think_deriver import (
        ThinkDeriver,
    )

    deriver = ThinkDeriver()
    events = [
        _think_event(
            event_id="run_x:10",
            execution_point="think.decision.repair",
            payload={"routing": {}},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "degraded"
    assert conditions[0].reason == "think_routing_empty"


def test_think_returns_failed_when_decision_repair_action_error() -> None:
    """A ``think.decision.repair`` whose routing has ``action_type=error`` is failed."""
    from lca.plugins.observability.health.derivers.think_deriver import (
        ThinkDeriver,
    )

    deriver = ThinkDeriver()
    events = [
        _think_event(
            event_id="run_x:11",
            execution_point="think.decision.repair",
            payload={"routing": {"action_type": "error", "message": "oops"}},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "failed"
    assert conditions[0].reason == "think_decision_error"


def test_think_returns_unknown_when_no_relevant_events() -> None:
    """No think.* events -> unknown."""
    from lca.plugins.observability.health.derivers.think_deriver import (
        ThinkDeriver,
    )

    deriver = ThinkDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "think"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "think_no_events"
    assert conditions[0].evidence_refs == ()


def test_think_takes_priority_failed_over_degraded() -> None:
    """When multiple repair events exist, the worst status wins.

    Ordering: ``failed`` > ``degraded`` > ``ok``. A failed decision
    repair in the presence of an empty one must not be silently
    upgraded to degraded.
    """
    from lca.plugins.observability.health.derivers.think_deriver import (
        ThinkDeriver,
    )

    deriver = ThinkDeriver()
    events = [
        _think_event(
            event_id="run_x:1",
            execution_point="think.decision.repair",
            payload={"routing": {}},
        ),
        _think_event(
            event_id="run_x:2",
            execution_point="think.decision.repair",
            payload={"routing": {"action_type": "error"}},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "failed"