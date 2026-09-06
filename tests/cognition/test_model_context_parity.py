"""ADR-0191 I-MV-RUNTIME-1: assembler output ≡ Session.derive_messages()."""

from __future__ import annotations

from lca.infrastructure.session.model_context_assembler import DefaultModelContextAssembler
from lca.plugins.session.runtime.messages import derive_messages
from lca.plugins.session.runtime.session import Session
from lca_kernel.events.fold import (
    REQUEST_HEADER_CATEGORY,
    SURFACE_ASSISTANT_TYPE,
    SURFACE_USER_TYPE,
)


def _recording_loop(session: Session) -> None:
    """Minimal fake loop surface events (tests/scenarios/test_recording_loop)."""
    session.append("turn.started.v1", {"turn": 1})
    session.append("step.started.v1", {"turn": 1, "step": 1})
    session.append("message.accepted.v1", {"message_id": "m1", "role": "user", "content_ref": "ping"})
    session.append(
        SURFACE_USER_TYPE,
        {"content": "ping", "messages": [{"role": "user", "content": "ping"}]},
        surface_op="append",
    )
    session.append(
        REQUEST_HEADER_CATEGORY,
        {
            "config": {"model": "test"},
            "system": "sys",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {"message": {"role": "assistant", "content": "pong"}},
        surface_op="append",
    )
    session.append("assistant.responded.v1", {"turn": 1, "step": 1, "content": "pong"})
    session.append("step.ended.v1", {"turn": 1, "step": 1})
    session.append("turn.ended.v1", {"turn": 1, "reason": "complete"})


def test_assembler_matches_derive_messages() -> None:
    session = Session("parity_1")
    _recording_loop(session)
    expected = derive_messages(session.snapshot_events())
    assembled = DefaultModelContextAssembler().assemble(session, step=1)
    assert assembled.messages == expected
    assert assembled.system == "sys"
    assert assembled.config == {"model": "test"}


def test_assembler_matches_session_derive_messages_incremental() -> None:
    session = Session("parity_2")
    _recording_loop(session)
    assembled = DefaultModelContextAssembler().assemble(session, step=1)
    assert assembled.messages == session.derive_messages()
