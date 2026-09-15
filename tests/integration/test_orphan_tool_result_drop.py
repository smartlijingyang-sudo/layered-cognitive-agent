"""Spec §D: orphan tool_result dropped before LLM call sees the wire shape.

A tool/result message whose ``tool_call_id`` is not present in any preceding
``assistant{tool_calls=[...]}`` row is an orphan. OpenAI's
``drop_orphan_function_calls`` pattern drops such rows at every LLM-call
preparation step so the wire shape never carries a dangling tool row.

The integration test drives ``RunSessionWriter`` against a minimal
``SessionProtocol`` and asserts that ``derive_messages()`` drops the
orphan before any caller sees the messages list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lca.runtime.session.run_session_writer import RunSessionWriter


@dataclass
class _StoredEvent:
    """Minimal SessionEvent shape for the writer test fixture."""

    type: str
    seq: int
    time: float
    data: dict[str, Any]
    surface_op: Any | None
    source_event_seqs: tuple[int, ...] | None


@dataclass
class _StoredHeader:
    """Minimal EpochHeader shape for ``request_header`` returns."""

    system: str | None


@dataclass
class _InMemorySession:
    """Minimal ``SessionProtocol`` for the writer test.

    Tracks every ``append`` call in ``events`` and exposes
    ``snapshot_events`` for ``derive_messages`` to walk. Mirrors the shape
    of :class:`lca.session.append.Session` minus durability + observers
    (not needed for orphan-drop projection).
    """

    events: list[_StoredEvent] = field(default_factory=list)
    system: str | None = None
    next_seq: int = 0

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        *,
        surface_op: Any | None = None,
        source_event_seqs: tuple[int, ...] | None = None,
    ) -> _StoredEvent:
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

    def snapshot_events(self) -> tuple[_StoredEvent, ...]:
        return tuple(self.events)

    def request_header(self) -> _StoredHeader | None:
        if self.system is None:
            return None
        return _StoredHeader(system=self.system)

    @property
    def id(self) -> str:
        return "test-session"


def test_orphan_tool_result_dropped_at_history_assemble() -> None:
    """[user, assistant{tool_calls=[X]}, tool{call_id=Y}] → orphan tool{Y} dropped.

    The assistant declared ``tool_calls=[X]``; the tool result has
    ``call_id=Y`` — a never-declared tool call. ``derive_messages`` must
    drop the tool row before it reaches the model-visible list.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    # Orphan: tool result with call_id="Y" that does not match the
    # assistant's declared tool call id "X".
    writer.append_tool_result(turn=0, step=0, call_id="Y", content="orphan", error=None, meta=None)

    msgs = writer.derive_messages()

    # Orphan dropped; only user + assistant remain in the wire shape.
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    # Assistant preserved with its declared tool_call (orphan-drop only
    # touches tool/result rows, not assistant rows).
    assert msgs[1]["tool_calls"] == [{"id": "X", "name": "bash", "arguments": "{}"}]


def test_non_orphan_tool_result_preserved() -> None:
    """[user, assistant{tool_calls=[X]}, tool{call_id=X}] → tool{X} preserved.

    Sanity check: orphan-drop is conservative; matched tool_call_id rows
    stay in the wire shape.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_assistant_message(
        turn=0,
        step=0,
        role="assistant",
        content=None,
        tool_calls=[{"id": "X", "name": "bash", "arguments": "{}"}],
        usage=None,
    )
    writer.append_tool_result(turn=0, step=0, call_id="X", content="ok", error=None, meta=None)

    msgs = writer.derive_messages()

    assert [m["role"] for m in msgs] == ["user", "assistant", "tool"]
    assert msgs[2]["tool_call_id"] == "X"


def test_orphan_tool_result_without_assistant_kept_in_journal_but_dropped_at_wire() -> None:
    """Orphan tool result stays in the journal for provenance, but drops at derive_messages.

    The journal holds the orphan event (so callers can debug the failure
    path); the wire shape projected by ``derive_messages`` does not.
    """
    session = _InMemorySession()
    writer = RunSessionWriter(session=session)
    writer.append_user_message(message_id="u1", role="user", content="hi")
    writer.append_tool_result(turn=0, step=0, call_id="Z", content="orphan", error=None, meta=None)

    # Journal holds the orphan event (provenance + audit trail).
    assert any(e.type == "surface/tool_result" for e in session.events)

    msgs = writer.derive_messages()

    # But the wire shape drops it (no preceding assistant declared tool_calls).
    assert [m["role"] for m in msgs] == ["user"]
