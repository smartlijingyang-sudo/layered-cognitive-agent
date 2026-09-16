"""Contract tests for ``PerceiveDeriver`` (PR-1 / Task 1.3).

Status rules (spec §10.4):
    ok       if ``phase.perceive.fold`` present
    unknown  if no ``perceive.*`` events
    degraded if ``phase.perceive.fold.start`` present but no fold close
              (not emitted by the current producer; reserved for v2)
    failed   if a perceive fold event carries an error outcome
              (not exercised in v1; reserved for v2)

The brief notes that ``degraded`` / ``failed`` paths are not exercised
in v1; we keep the test slot so the 4-case schema is uniform across
derivers, but assert the v1 behaviour explicitly.
"""

from __future__ import annotations

import pytest

from lca.contracts.observability.health.condition import (
    RunHealthCondition as RunHealthCondition,
)
from lca.contracts.observability.health.condition import (
    RunHealthStatus as RunHealthStatus,
)
from lca.contracts.observability.health.evidence_ref import EvidenceRef
from lca.plugins.observability.health.derivers._spine import SpineEvent


def _perceive_event(
    *,
    event_id: str = "run_3383288d63e7:18",
    ts: str = "2026-09-16T02:49:35.837507+00:00",
    run_id: str = "run_3383288d63e7",
    payload: dict | None = None,
) -> SpineEvent:
    return SpineEvent(
        event_id=event_id,
        ts=ts,
        run_id=run_id,
        execution_point="phase.perceive.fold",
        payload=payload if payload is not None else {"state_id": "trace_x"},
    )


def test_perceive_returns_ok_when_perceive_phase_fold_end_present() -> None:
    """Happy path: a perceive fold EP exists."""
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    deriver = PerceiveDeriver()
    events = [_perceive_event()]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "perceive"
    assert conditions[0].status == "ok"
    assert conditions[0].reason == "perceive_fold_closed"
    assert len(conditions[0].evidence_refs) >= 1
    ref = conditions[0].evidence_refs[0]
    assert isinstance(ref, EvidenceRef)
    assert ref.execution_point == "phase.perceive.fold"


def test_perceive_returns_unknown_when_no_relevant_events() -> None:
    """No perceive.* events at all -> unknown (reflect/remember may be absent)."""
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    deriver = PerceiveDeriver()
    events: list[SpineEvent] = []  # no events at all
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].type == "perceive"
    assert conditions[0].status == "unknown"
    # Unknown has no evidence (the EP that would justify the condition is missing).
    assert conditions[0].evidence_refs == ()


def test_perceive_ignores_non_perceive_events() -> None:
    """Only perceive.* EPs are consumed; think/act/tool etc. ignored."""
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    deriver = PerceiveDeriver()
    events = [
        SpineEvent(
            event_id="run_x:1",
            ts="2026-09-16T02:49:35.000000+00:00",
            run_id="run_x",
            execution_point="phase.think.fold",
            payload={},
        ),
        SpineEvent(
            event_id="run_x:2",
            ts="2026-09-16T02:49:36.000000+00:00",
            run_id="run_x",
            execution_point="step.tool_call.record",
            payload={"invocation_id": "toolu_abc"},
        ),
    ]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    assert conditions[0].status == "unknown"


def test_perceive_evidence_carries_full_run_id_and_seq() -> None:
    """The evidence_ref.run_id and seq round-trip from the spine event_id."""
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    deriver = PerceiveDeriver()
    events = [_perceive_event(event_id="run_abc123def:42", run_id="run_abc123def")]
    conditions = deriver.evaluate(events)
    assert len(conditions) == 1
    ref = conditions[0].evidence_refs[0]
    assert ref.run_id == "run_abc123def"
    assert ref.event_id == "run_abc123def:42"
    assert ref.seq == 42


def test_perceive_status_is_closed_alphabet() -> None:
    """The status field satisfies the closed 4-value literal."""
    from lca.plugins.observability.health.derivers.perceive_deriver import (
        PerceiveDeriver,
    )

    deriver = PerceiveDeriver()
    ok_status = deriver.evaluate([_perceive_event()])[0].status
    unknown_status = deriver.evaluate([])[0].status
    valid: set[RunHealthStatus] = {"ok", "degraded", "failed", "unknown"}
    assert ok_status in valid
    assert unknown_status in valid