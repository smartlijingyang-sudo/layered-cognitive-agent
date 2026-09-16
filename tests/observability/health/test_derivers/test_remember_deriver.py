"""Contract tests for ``RememberDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4): same shape as ``reflect`` — the phase is
optional in some profiles; ``degraded`` / ``failed`` are not
exercised in v1.
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _remember_event(
    *,
    event_id: str = "run_x:1",
    ts: str = "2026-09-16T02:49:35.000000+00:00",
    run_id: str = "run_x",
    execution_point: str = "phase.remember.fold",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {"phase": "remember"},
    )


def test_remember_returns_ok_when_remember_fold_end_present() -> None:
    """A ``phase.remember.fold`` event closes the phase -> ok."""
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    deriver = RememberDeriver()
    events = [_remember_event()]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "remember"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "remember_fold_closed"
    assert conditions[0].evidence_refs[0].execution_point == "phase.remember.fold"


def test_remember_returns_unknown_when_no_relevant_events() -> None:
    """No remember.* events -> unknown."""
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    deriver = RememberDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "remember"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "remember_no_events"
    assert conditions[0].evidence_refs == ()


def test_remember_ignores_non_remember_events() -> None:
    """Only remember.* EPs are consumed."""
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    deriver = RememberDeriver()
    events = [
        _remember_event(
            event_id="run_x:1",
            execution_point="phase.think.fold",
        ),
        _remember_event(
            event_id="run_x:2",
            execution_point="phase.reflect.fold",
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "unknown"


def test_remember_evidence_seq_round_trips() -> None:
    """``EvidenceRef.seq`` parses correctly from the spine event_id."""
    from lca.plugins.observability.health.derivers.remember_deriver import (
        RememberDeriver,
    )

    deriver = RememberDeriver()
    events = [_remember_event(event_id="run_q:200", run_id="run_q")]
    conditions = deriver.evaluate(events)
    assert conditions[0].evidence_refs[0].seq == 200
    assert conditions[0].evidence_refs[0].run_id == "run_q"
