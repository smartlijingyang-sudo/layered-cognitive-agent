"""Session lifecycle emit tests (DSH spec §5 / recording loop parity)."""

from __future__ import annotations

from lca.contracts.harness.collaboration.agent import LiveAgentStatus
from lca.contracts.harness.memory.events import ThinkingCompleted, ThinkingDelta
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import Budget, StateSnapshot
from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseRunCursor
from lca.infrastructure.session.lifecycle_emit import (
    accept_user_message,
    begin_turn,
    checkpoint,
    complete_model,
    create_session,
    emit_approval_pause_from_result,
    end_step,
    end_turn,
    fail_model,
    persist_approval,
    request_model,
    reset_lifecycle,
    session_append_for_thinking,
    terminal_checkpoint_status,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.messages import derive_messages
from lca.session.recovery import recover_live_agent
from lca.session.append import Session


def test_lifecycle_emit_noop_when_session_unbound() -> None:
    reset_lifecycle()
    begin_turn()
    accept_user_message(message_id="m0", content="ignored")
    request_model(step=1, provider="test", model="m")
    complete_model(step=1, content="ignored")
    end_step(step=1)
    end_turn()
    assert create_session("profiles/test.yaml") is None
    assert checkpoint("completed") is None
    assert persist_approval("ap-0", {"approval_id": "ap-0"}) is None

    append = session_append_for_thinking()
    append(ThinkingDelta(turn=1, step=1, text_delta="x", seq=0))
    append(ThinkingCompleted(turn=1, step=1, duration_ms=1, content_preview="x"))


def test_lifecycle_emit_full_turn_sequence() -> None:
    session = Session("lifecycle_1")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        begin_turn()
        accept_user_message(message_id="m1", content="ping")
        request_model(step=1, provider="test", model="m")
        complete_model(step=1, content="pong")
        end_step(step=1)
        end_turn(reason="completed")

        types = [event.type for event in session.snapshot_events()]
        assert "turn.started.v1" in types
        assert "message.accepted.v1" in types
        assert "step.started.v1" in types
        assert "model.requested.v1" in types
        assert "model.completed.v1" in types
        assert "assistant.responded.v1" in types
        assert "step.ended.v1" in types
        assert "turn.ended.v1" in types
        messages = derive_messages(session.snapshot_events())
        assert messages and messages[-1]["role"] == "assistant"
    finally:
        reset_publish_session(token)


def test_lifecycle_emit_idempotent_turn_and_message() -> None:
    session = Session("lifecycle_2")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        begin_turn()
        begin_turn()
        accept_user_message(message_id="m1", content="once")
        accept_user_message(message_id="m2", content="ignored")
        assert sum(1 for e in session.snapshot_events() if e.type == "turn.started.v1") == 1
        assert sum(1 for e in session.snapshot_events() if e.type == "message.accepted.v1") == 1
    finally:
        reset_publish_session(token)


def test_create_session_emits_catalog_event() -> None:
    session = Session("lifecycle_3")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        created = create_session("profiles/web-app.yaml", preset="solo")
        assert created is not None
        assert created.profile == "profiles/web-app.yaml"
        assert created.preset == "solo"
        events = session.snapshot_events()
        assert len(events) == 1
        assert events[0].type == "session.created.v1"
        assert events[0].data["profile"] == "profiles/web-app.yaml"
    finally:
        reset_publish_session(token)


def test_checkpoint_and_terminal_status_mapping() -> None:
    session = Session("lifecycle_4")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        checkpoint("completed")
        assert terminal_checkpoint_status(TaskStatus.COMPLETED) == "completed"
        assert terminal_checkpoint_status(TaskStatus.INPUT_REQUIRED) is None
        assert session.snapshot_events()[-1].type == "session.checkpoint.v1"
        assert session.snapshot_events()[-1].data["status"] == "completed"
    finally:
        reset_publish_session(token)


def test_emit_approval_pause_from_result_recovers_waiting_input() -> None:
    session = Session("lifecycle_5")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        cursor = PhaseRunCursor(
            plan_ref="plan-1",
            node_id="think.standard",
            visit_counts=(("think.standard", 1),),
            edge_counts=(),
            artifacts={},
            causation_refs=(),
            budget_snapshot={},
        )
        snapshot = StateSnapshot(
            snapshot_id="snap-1",
            step=2,
            state_ref="state://saved",
            phase_cursor=cursor,
            trace_id="trace-1",
        )
        result = Result(
            trace_id="trace-1",
            status=TaskStatus.INPUT_REQUIRED,
            final_state_ref="state://saved",
            total_steps=3,
            budget_used=Budget(),
            extra={
                "approval_request": {"approval_id": "ap-1", "type": "tool_approval"},
                "state_snapshot": snapshot,
            },
        )
        emit_approval_pause_from_result(result)
        emit_approval_pause_from_result(result)
        events = list(session.snapshot_events())
        assert sum(1 for e in events if e.type == "approval.persisted.v1") == 1
        assert sum(1 for e in events if e.type == "session.checkpoint.v1") == 1
        view = recover_live_agent(events)
        assert view.status is LiveAgentStatus.WAITING_INPUT
        assert view.pending_resume is not None
        assert view.pending_resume.approval_id == "ap-1"
    finally:
        reset_publish_session(token)


def test_persist_approval_emits_resume_point() -> None:
    session = Session("lifecycle_6")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        resume_point = {
            "approval_id": "ap-2",
            "snapshot_id": "snap-2",
            "step": 1,
            "state_ref": "state-2",
            "plan_ref": "plan-2",
            "node_id": "node-2",
            "visit_counts": [],
            "edge_counts": [],
            "artifacts": {},
            "causation_refs": [],
            "budget_snapshot": {},
        }
        persisted = persist_approval("ap-2", resume_point)
        assert persisted is not None
        event = session.snapshot_events()[-1]
        assert event.type == "approval.persisted.v1"
        assert event.data["approval_id"] == "ap-2"
        assert event.data["resume_point"]["node_id"] == "node-2"
    finally:
        reset_publish_session(token)


def test_session_append_for_thinking_emits_catalog_events() -> None:
    session = Session("lifecycle_7")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        append = session_append_for_thinking()
        append(ThinkingDelta(turn=1, step=2, text_delta="a", seq=0))
        events = session.snapshot_events()
        assert len(events) == 1
        assert events[0].type == "thinking.delta.v1"
        assert events[0].data["text_delta"] == "a"
    finally:
        reset_publish_session(token)


def test_session_append_for_thinking_emits_delta_and_completed() -> None:
    session = Session("thinking_1")
    token = set_publish_session(session)
    try:
        append = session_append_for_thinking()
        append(ThinkingDelta(turn=1, step=2, text_delta="a", seq=0))
        append(ThinkingDelta(turn=1, step=2, text_delta="b", seq=1))
        append(
            ThinkingCompleted(
                turn=1,
                step=2,
                duration_ms=10,
                content_preview="ab",
            )
        )

        types = [event.type for event in session.snapshot_events()]
        assert types.count("thinking.delta.v1") == 2
        assert types.count("thinking.completed.v1") == 1
    finally:
        reset_publish_session(token)


def test_fail_model_emits_model_failed() -> None:
    session = Session("fail_1")
    token = set_publish_session(session)
    try:
        reset_lifecycle()
        fail_model(step=3, error="provider down")

        events = session.snapshot_events()
        failed = [e for e in events if e.type == "model.failed.v1"]
        assert len(failed) == 1
        assert failed[0].data["step"] == 3
        assert failed[0].data["error"] == "provider down"
    finally:
        reset_publish_session(token)
