"""Recovery integration tests (ADR-0191 Wave B3 / I-RESUME-3)."""

from __future__ import annotations

from lca.contracts.harness.collaboration.agent import LiveAgentStatus
from lca.contracts.harness.tasks.session import SessionEvent
from lca.session.lifecycle.recovery import recover_live_agent
from lca.session.lifecycle.repair import repair_interrupted_turn

_SESSION = "recovery-run"


def _event(seq: int, event_type: str, data: dict) -> SessionEvent:
    return SessionEvent(
        type=event_type,
        seq=seq,
        time=seq,
        data=data,
        session_id=_SESSION,
    )


def test_recover_live_agent_after_repair_closes_open_turn() -> None:
    """Cold restore repair + recover_live_agent yields an idle, resumable view."""
    raw = [
        _event(0, "turn.started.v1", {"turn": 1}),
        _event(1, "step.started.v1", {"turn": 1, "step": 1}),
    ]
    repaired = list(raw) + repair_interrupted_turn(raw)
    view = recover_live_agent(repaired)

    assert view.status is LiveAgentStatus.IDLE
    assert view.completed_turns == 1
    assert view.pending_resume is None


def test_recover_live_agent_waiting_input_with_approval() -> None:
    raw = [
        _event(0, "turn.started.v1", {"turn": 1}),
        _event(1, "turn.ended.v1", {"turn": 1, "reason": "paused"}),
        _event(
            2,
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
        _event(3, "session.checkpoint.v1", {"status": "waiting_input"}),
    ]
    view = recover_live_agent(raw)

    assert view.status is LiveAgentStatus.WAITING_INPUT
    assert view.pending_resume is not None
    assert view.pending_resume.approval_id == "ap-1"


def test_bind_run_emits_session_created() -> None:
    from lca.session.lifecycle.bind import (
        bind_run_event_session_from_store,
        unbind_run_event_session,
    )
    from lca.plugins.session.runtime.store.store import SessionStore

    store = SessionStore()
    bound = bind_run_event_session_from_store(
        store,
        "recovery_bind",
        profile="profiles/test.yaml",
        preset="solo",
    )
    try:
        events = bound.bridge.inner.snapshot_events()
        assert len(events) == 1
        assert events[0].type == "session.created.v1"
        assert events[0].data["profile"] == "profiles/test.yaml"
        assert events[0].data["preset"] == "solo"
    finally:
        unbind_run_event_session(bound)
