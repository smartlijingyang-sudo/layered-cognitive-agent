"""Tests for RunSessionWriter.seed_prior_turns (ADR-0244 PR-2 Task 5).

Verifies that prior conversation turns are injected into the Session as
first-class surface events with historical=True, and reflected in derive_messages().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.contracts.models.core.conversation.conversation import ConversationTurn
from lca.runtime.session.run_session_writer import (
    RunSessionWriter,
    SessionWriterUnboundError,
)


@dataclass
class _InMemorySession:
    events: list[Any] = field(default_factory=list)
    next_seq: int = 0

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> Any:
        event = _StoredEvent(
            type=event_type,
            seq=self.next_seq,
            time=self.next_seq * 1000.0,
            data=dict(data),
            surface_op=surface_op,
            source_event_seqs=source_event_seqs,
        )
        self.next_seq += 1
        self.events.append(event)
        return event

    def snapshot_events(self) -> tuple[Any, ...]:
        return tuple(self.events)

    @property
    def id(self) -> str:
        return "test-session-prior"


@dataclass
class _StoredEvent:
    type: str
    seq: int
    time: float
    data: dict[str, Any]
    surface_op: Any | None
    source_event_seqs: tuple[int, ...] | None


def test_seed_prior_turns_injects_surface_events_and_preserves_messages() -> None:
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)

    turns = (
        ConversationTurn(role="user", content="请帮我写一个 python 脚本"),
        ConversationTurn(role="assistant", content="好的，请问脚本要实现什么功能？"),
    )

    writer.seed_prior_turns(turns)

    # Verify session events appended
    assert len(session.events) == 2
    ev0 = session.events[0]
    assert ev0.type == "surface/user_message"
    assert ev0.data["role"] == "user"
    assert ev0.data["content"] == "请帮我写一个 python 脚本"
    assert ev0.data["historical"] is True

    ev1 = session.events[1]
    assert ev1.type == "surface/assistant_message"
    assert ev1.data["role"] == "assistant"
    assert ev1.data["content"] == "好的，请问脚本要实现什么功能？"
    assert ev1.data["historical"] is True

    # Then the current turn is appended
    writer.append_user_message(
        message_id="task:current",
        role="user",
        content="实现一个解析 PDF 的脚本",
    )

    # Verify derive_messages reflects all 3 messages in chronological order
    messages = writer.derive_messages()
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "请帮我写一个 python 脚本"}
    assert messages[1] == {"role": "assistant", "content": "好的，请问脚本要实现什么功能？"}
    assert messages[2] == {"role": "user", "content": "实现一个解析 PDF 的脚本"}


def test_seed_prior_turns_idempotent() -> None:
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)

    turns = (ConversationTurn(role="user", content="hello"),)
    writer.seed_prior_turns(turns)
    assert len(session.events) == 1

    # Calling again should be a no-op
    writer.seed_prior_turns(turns)
    assert len(session.events) == 1


def test_seed_prior_turns_empty_is_noop() -> None:
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)

    writer.seed_prior_turns(())
    assert len(session.events) == 0


def test_seed_prior_turns_unbound_raises() -> None:
    writer = RunSessionWriter(session=None)
    with pytest.raises(SessionWriterUnboundError):
        writer.seed_prior_turns((ConversationTurn(role="user", content="hello"),))
