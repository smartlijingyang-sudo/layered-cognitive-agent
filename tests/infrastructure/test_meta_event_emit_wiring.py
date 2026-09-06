"""Meta-event emit wiring against bound Session."""

from __future__ import annotations

from lca.infrastructure.observability.meta_event_emit import (
    emit_attachment_committed,
    emit_command_rejected,
    emit_context_injected,
    emit_feedback_record,
    emit_inbox_spliced,
    emit_skill_routed,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


def test_meta_emit_skill_routed_and_context() -> None:
    session = Session("meta_emit_1")
    token = set_publish_session(session)
    try:
        emit_skill_routed(template_id="react_prompt", decision_path="static")
        emit_context_injected(source="perceive", content_ref="manifest:abc")
        types = [event.type for event in session.snapshot_events()]
        assert "skill.routed.v1" in types
        assert "context.injected.v1" in types
    finally:
        reset_publish_session(token)


def test_meta_emit_transport_catalog_events() -> None:
    session = Session("meta_emit_2")
    token = set_publish_session(session)
    try:
        emit_attachment_committed(
            attachment_id="att_1",
            name="doc.pdf",
            size_bytes=42,
            mime_type="application/pdf",
        )
        emit_inbox_spliced(
            op="append",
            target="next_turn",
            message_ids=("inbox-1",),
            messages=({"role": "user", "content": "hi"},),
        )
        emit_command_rejected(command_type="resume_approval", reason="not_waiting_input")
        emit_feedback_record(text="good", rating="up")
        types = [event.type for event in session.snapshot_events()]
        assert "attachment.committed.v1" in types
        assert "inbox.spliced.v1" in types
        assert "command.rejected.v1" in types
        assert "feedback.record.v1" in types
    finally:
        reset_publish_session(token)
