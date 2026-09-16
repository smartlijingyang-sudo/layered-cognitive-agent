"""Contract tests for ``ActDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4):

    ok       if ``act.fanout`` payload has ``routing.next_hint ==
             "fanout_ntom"``, OR no ``act.fanout`` events are present
             (the act phase ran without fanout — single tool dispatch).
    degraded if ``routing.next_hint == "fanout_1to1"`` — fanout
             collapsed to a single tool (warning, not failure).
    failed   if ``routing.next_hint == "fanout_empty"`` — fanout
             unexpectedly produced no dispatchable tool calls.
    unknown  if no ``act.*`` events at all.

The v1 producer emits ``phase.act.fold`` and ``phase.act.fold.end`` in
addition to ``act.fanout``; the deriver accepts any of these as
"act phase ran". When ``act.fanout`` is present, its routing next_hint
overrides the fold evidence.
"""

from __future__ import annotations

from lca.plugins.observability.health.derivers._spine import SpineEvent


def _act_event(
    *,
    event_id: str = "run_3383288d63e7:227",
    ts: str = "2026-09-16T02:50:14.069614+00:00",
    run_id: str = "run_3383288d63e7",
    execution_point: str = "phase.act.fold.end",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point=execution_point,
        payload=payload if payload is not None else {"outcome": "success"},
    )


def test_act_returns_ok_when_act_fold_end_present() -> None:
    """Happy path: act fold closed successfully without an act.fanout event."""
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    deriver = ActDeriver()
    events = [_act_event()]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "act"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "act_fold_closed"
    assert conditions[0].evidence_refs[0].execution_point == "phase.act.fold.end"


def test_act_returns_ok_when_fanout_ntom() -> None:
    """``act.fanout`` with ``next_hint == "fanout_ntom"`` is the new ok path."""
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    deriver = ActDeriver()
    events = [
        _act_event(
            event_id="run_x:5",
            execution_point="act.fanout",
            payload={"routing": {"next_hint": "fanout_ntom", "count": 3}},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "act_fanout_ntom"


def test_act_returns_degraded_when_fanout_1to1() -> None:
    """``act.fanout`` with ``next_hint == "fanout_1to1"`` is degraded."""
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    deriver = ActDeriver()
    events = [
        _act_event(
            event_id="run_x:5",
            execution_point="act.fanout",
            payload={"routing": {"next_hint": "fanout_1to1"}},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "degraded"
    assert conditions[0].reason == "act_fanout_1to1"


def test_act_returns_failed_when_fanout_empty() -> None:
    """``act.fanout`` with ``next_hint == "fanout_empty"`` is failed."""
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    deriver = ActDeriver()
    events = [
        _act_event(
            event_id="run_x:5",
            execution_point="act.fanout",
            payload={"routing": {"next_hint": "fanout_empty"}},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "failed"
    assert conditions[0].reason == "act_fanout_empty"


def test_act_returns_unknown_when_no_relevant_events() -> None:
    """No act.* events at all -> unknown."""
    from lca.plugins.observability.health.derivers.act_deriver import ActDeriver

    deriver = ActDeriver()
    events: list[SpineEvent] = []
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "act"
    assert conditions[0].status == "unknown"
    assert conditions[0].reason == "act_no_events"
    assert conditions[0].evidence_refs == ()
