"""Tests for ``RunSessionWriter`` (spec §B, ADR-0226 §1).

Each test exercises one method of the writer against an in-memory session
that satisfies :class:`SessionProtocol`. The ``derive_messages`` test stays
xfail until Task 2 fills in the orphan-drop projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from lca.runtime.session.run_session_writer import (
    RunSessionWriter,
    SessionWriterUnboundError,
)


@dataclass
class _InMemorySession:
    """Minimal ``SessionProtocol`` for writer tests.

    Tracks every ``append`` call in ``events`` and exposes ``last_event`` for
    the brief's assertion style. Optional ``system`` keyword simulates a
    pre-folded :class:`EpochHeader` returned from ``request_header``.
    """

    events: list[Any] = field(default_factory=list)
    system: str | None = None
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

    def last_event(self) -> Any:
        assert self.events, "no events appended"
        return self.events[-1]

    def request_header(self) -> Any | None:
        if self.system is None:
            return None
        return _StoredHeader(system=self.system)

    def snapshot_events(self) -> tuple[Any, ...]:
        return tuple(self.events)

    @property
    def id(self) -> str:
        return "test-session"


@dataclass
class _StoredEvent:
    type: str
    seq: int
    time: float
    data: dict[str, Any]
    surface_op: Any | None
    source_event_seqs: tuple[int, ...] | None


@dataclass
class _StoredHeader:
    system: str | None


def test_unbound_writer_raises_session_writer_unbound_error() -> None:
    """A writer constructed with no Session raises fail-loud, not silent None."""
    writer = RunSessionWriter(session=None)
    with pytest.raises(SessionWriterUnboundError):
        writer.append_user_message(message_id="m1", role="user", content="hi")


def test_append_user_message_writes_surface_user_message() -> None:
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    ref = writer.append_user_message(message_id="m1", role="user", content="hi")
    assert ref.event_id == "test-session:0"
    assert ref.category == "surface/user_message"
    assert session.last_event().type == "surface/user_message"
    assert session.last_event().data["content"] == "hi"
    assert session.last_event().data["message_id"] == "m1"
    assert session.last_event().data["role"] == "user"
    assert session.last_event().surface_op == "user_message"


def test_append_assistant_message_with_tool_calls_writes_tool_calls_in_payload() -> None:
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    ref = writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "c1", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    event = session.last_event()
    assert ref.category == "surface/assistant_message"
    assert event.type == "surface/assistant_message"
    assert event.data["tool_calls"][0]["id"] == "c1"
    assert event.data["content"] is None
    assert event.surface_op == "assistant_message"


def test_append_tool_call_writes_log_only_event() -> None:
    """log/tool_call is NOT a surface event; it pairs surface/tool_result via source_event_seqs."""
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    ref = writer.append_tool_call(
        turn=0, step=0, call_id="c1", name="bash", arguments="{}"
    )
    event = session.last_event()
    assert ref.category == "log/tool_call"
    assert event.type == "log/tool_call"
    assert event.surface_op is None  # NOT a surface event


def test_append_tool_result_links_to_assistant_via_source_event_seqs() -> None:
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "c1", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    ref = writer.append_tool_result(
        turn=0, step=0, call_id="c1", content="ok", error=None, meta=None
    )
    event = session.last_event()
    assert ref.category == "surface/tool_result"
    assert event.type == "surface/tool_result"
    assert event.data["tool_call_id"] == "c1"
    assert event.source_event_seqs  # populated for pairing provenance
    assert event.source_event_seqs == (0,)  # links to the assistant row's seq


@pytest.mark.xfail(reason="Implemented in Task 2")
def test_derive_messages_returns_wire_shape() -> None:
    """derive_messages() returns the OpenAI-compatible messages list."""
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="m1", role="user", content="hello")
    writer.append_assistant_message(
        turn=0, step=0, role="assistant", content="hi",
        tool_calls=None, usage=None,
    )
    msgs = writer.derive_messages()
    assert msgs == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi", "tool_calls": None},
    ]


def test_request_header_returns_epoch_header_system_field() -> None:
    session = _InMemorySession(system="You are a helpful assistant.")
    writer = RunSessionWriter(session=session)
    header = writer.request_header()
    assert header is not None
    assert header.system == "You are a helpful assistant."
