"""Transport resume validates Session recovery facts (ADR-0191 Wave B3)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.harness.tasks.session import SessionEvent
from lca.session.recovery import SessionRecoveryError, assert_resume_allowed
from lca.contracts.observability.status import RunLifecycleStatus


def _event(seq: int, event_type: str, data: dict) -> SessionEvent:
    return SessionEvent(
        session_id="run_1",
        seq=seq,
        type=event_type,
        time=float(seq),
        data=data,
        actor="test",
        visibility="internal",
    )


@dataclass
class _RunStub:
    status: RunLifecycleStatus


def test_assert_resume_allowed_syncs_status() -> None:
    session = _RunStub(status=RunLifecycleStatus.WAITING_INPUT)
    events = [
        _event(
            0,
            "approval.persisted.v1",
            {
                "approval_id": "ap-1",
                "resume_point": {
                    "approval_id": "ap-1",
                    "snapshot_id": "snap-1",
                    "step": 1,
                    "state_ref": "state-1",
                    "plan_ref": "plan-1",
                    "node_id": "node-1",
                    "visit_counts": [],
                    "edge_counts": [],
                    "artifacts": {},
                    "causation_refs": [],
                    "budget_snapshot": {},
                },
            },
        ),
        _event(1, "session.checkpoint.v1", {"status": "waiting_input"}),
    ]
    assert_resume_allowed(session, events)
    assert session.status is RunLifecycleStatus.WAITING_INPUT


def test_assert_resume_allowed_rejects_idle_recovery() -> None:
    session = _RunStub(status=RunLifecycleStatus.WAITING_INPUT)
    events = [_event(0, "turn.ended.v1", {"turn": 1, "reason": "completed"})]
    with pytest.raises(SessionRecoveryError):
        assert_resume_allowed(session, events)


def test_append_approval_resolved_if_pending() -> None:
    from lca.plugins.session.runtime.session import Session
    from lca.plugins.session.runtime.transport_recovery import append_approval_resolved_if_pending

    session = Session("run_2")
    events = [
        _event(
            0,
            "approval.persisted.v1",
            {
                "approval_id": "ap-2",
                "resume_point": {
                    "approval_id": "ap-2",
                    "snapshot_id": "snap-2",
                    "step": 2,
                    "state_ref": "state-2",
                    "plan_ref": "plan-2",
                    "node_id": "node-2",
                    "visit_counts": [],
                    "edge_counts": [],
                    "artifacts": {},
                    "causation_refs": [],
                    "budget_snapshot": {},
                },
            },
        ),
        _event(1, "session.checkpoint.v1", {"status": "waiting_input"}),
    ]
    assert append_approval_resolved_if_pending(
        session,
        events,
        approval_id="ap-2",
        payload="yes",
        command_id="cmd-1",
    )
    appended = list(session.snapshot_events())
    assert appended[-1].type == "approval.resolved.v1"
    assert appended[-1].data["approved"] is True
