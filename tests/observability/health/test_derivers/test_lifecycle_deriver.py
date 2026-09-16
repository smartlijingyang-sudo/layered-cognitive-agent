"""Contract tests for ``LifecycleDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4):

    ok       if ``kernel.run.stop`` payload has ``outcome == "success"``
    failed   if outcome is in {failed, error, failure, timeout, ...}
             (anything not "success")
    unknown  if no ``kernel.run.stop`` event
    degraded reserved for ``outcome == "degraded"`` (not emitted in v1)
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _lifecycle_event(
    *,
    event_id: str = "run_3383288d63e7:698",
    ts: str = "2026-09-16T02:49:49.038669+00:00",
    run_id: str = "run_3383288d63e7",
    execution_point: str = "kernel.run.stop",
    outcome: str = "success",
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload={"outcome": outcome, "run_id": run_id},
    )


def test_lifecycle_returns_ok_when_kernel_run_stop_outcome_success() -> None:
    """Happy path: ``kernel.run.stop`` with outcome="success" -> ok."""
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    deriver = LifecycleDeriver()
    events = [_lifecycle_event()]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "lifecycle"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "lifecycle_outcome_success"
    assert conditions[0].evidence_refs[0].execution_point == "kernel.run.stop"


def test_lifecycle_returns_failed_when_outcome_failed() -> None:
    """``outcome == "failed"`` -> failed."""
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    deriver = LifecycleDeriver()
    events = [_lifecycle_event(outcome="failed")]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "failed"
    assert conditions[0].reason == "lifecycle_outcome_failed"


def test_lifecycle_returns_failed_when_outcome_timeout() -> None:
    """``outcome == "timeout"`` -> failed (any non-success is failed)."""
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    deriver = LifecycleDeriver()
    events = [_lifecycle_event(outcome="timeout")]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "failed"


def test_lifecycle_returns_unknown_when_no_relevant_events() -> None:
    """No ``kernel.run.stop`` event -> unknown."""
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    deriver = LifecycleDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "lifecycle"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "lifecycle_no_events"
    assert conditions[0].evidence_refs == ()


def test_lifecycle_takes_last_outcome_when_multiple_stops() -> None:
    """When multiple ``kernel.run.stop`` events exist, the last wins.

    A run may have multiple stop events during recovery; the
    health report is the final terminal outcome. (Single-condition
    invariant from spec §10.5 property 2.)
    """
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    deriver = LifecycleDeriver()
    events = [
        _lifecycle_event(event_id="run_x:1", outcome="failed"),
        _lifecycle_event(event_id="run_x:2", outcome="success"),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "ok"
    assert conditions[0].evidence_refs[0].event_id == "run_x:2"


def test_lifecycle_ignores_lifecycle_finally() -> None:
    """Only ``kernel.run.stop`` drives the lifecycle status; ``lifecycle.finally``
    is consumed by the fold's lifecycle normalization (per spec §10.4),
    not by this deriver."""
    from lca.plugins.observability.health.derivers.lifecycle_deriver import (
        LifecycleDeriver,
    )

    deriver = LifecycleDeriver()
    events = [
        SpineEvent(
            event_id="run_x:1",
            ts="2026-09-16T02:49:49.000000+00:00",
            run_id="run_x",
            execution_point="lifecycle.finally",
            payload={"outcome": "success"},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "unknown"