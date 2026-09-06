"""Session lifecycle emit tests (DSH spec §5 / recording loop parity)."""

from __future__ import annotations

from lca.infrastructure.session.lifecycle_emit import (
    accept_user_message,
    begin_turn,
    complete_model,
    end_step,
    end_turn,
    request_model,
    reset_lifecycle,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.messages import derive_messages
from lca.plugins.session.runtime.session import Session


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
