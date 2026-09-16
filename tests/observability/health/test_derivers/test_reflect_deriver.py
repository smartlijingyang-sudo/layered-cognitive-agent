"""Contract tests for ``ReflectDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4):

    ok       if ``reflect.*.fold.end`` is present
    unknown  if no ``reflect.*`` events (reflect may be absent in
             some profiles — v1 leaves the phase optional)
    degraded ``fold.start`` present but no fold close (not exercised
             in v1; the v1 producer does not emit the start/end pair)
    failed   fold.end present with error outcome (not exercised in v1)

The 4-case schema is kept for uniformity across derivers even though
the v1 producer collapses ``degraded`` / ``failed`` to ``unknown`` /
``ok`` respectively.
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _reflect_event(
    *,
    event_id: str = "run_x:1",
    ts: str = "2026-09-16T02:49:35.000000+00:00",
    run_id: str = "run_x",
    execution_point: str = "phase.reflect.fold",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {"phase": "reflect"},
    )


def test_reflect_returns_ok_when_reflect_fold_end_present() -> None:
    """A ``phase.reflect.fold`` event closes the phase -> ok."""
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    deriver = ReflectDeriver()
    events = [_reflect_event()]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "reflect"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "reflect_fold_closed"
    assert conditions[0].evidence_refs[0].execution_point == "phase.reflect.fold"


def test_reflect_returns_unknown_when_no_relevant_events() -> None:
    """No reflect.* events -> unknown (phase may be absent in profile)."""
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    deriver = ReflectDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "reflect"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "reflect_no_events"
    assert conditions[0].evidence_refs == ()


def test_reflect_ignores_non_reflect_events() -> None:
    """Only reflect.* EPs are consumed."""
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    deriver = ReflectDeriver()
    events = [
        _reflect_event(
            event_id="run_x:1",
            execution_point="phase.think.fold",
        ),
        _reflect_event(
            event_id="run_x:2",
            execution_point="phase.act.fold",
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "unknown"


def test_reflect_evidence_seq_round_trips() -> None:
    """``EvidenceRef.seq`` parses correctly from the spine event_id."""
    from lca.plugins.observability.health.derivers.reflect_deriver import (
        ReflectDeriver,
    )

    deriver = ReflectDeriver()
    events = [_reflect_event(event_id="run_zzz:99", run_id="run_zzz")]
    conditions = deriver.evaluate(events)
    assert conditions[0].evidence_refs[0].seq == 99
    assert conditions[0].evidence_refs[0].run_id == "run_zzz"