"""MemoryJournalReceipt commit tests (ADR-0194 P1-13)."""

from __future__ import annotations

from lca.contracts.models.observability.journal.journal import ContextCompacted, MemoryCommitted
from lca.contracts.models.observability.memory.memory_journal_receipt import (
    MemoryJournalReceipt,
    MemorySpineReceipt,
    context_compacted_receipt,
    memory_committed_receipt,
    memory_read_spine_receipt,
)
from lca.loop.commit.memory_journal import (
    commit_memory_journal_receipt,
    commit_memory_spine_receipt,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


def test_commit_memory_journal_receipt_uses_fact_gateway() -> None:
    session = Session("t-memory-committed-1")
    token = set_publish_session(session)
    try:
        receipt = memory_committed_receipt(layer="working", record_id="rec-1")
        result = commit_memory_journal_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "memory.committed.v1"
        assert event.data["record_id"] == "rec-1"
    finally:
        reset_publish_session(token)


def test_commit_memory_journal_receipt_noop_when_unbound() -> None:
    receipt = MemoryJournalReceipt(
        journal_event=MemoryCommitted(layer="working", record_id="rec-2"),
    )
    assert commit_memory_journal_receipt(receipt) is None


def test_commit_context_compacted_receipt() -> None:
    session = Session("t-memory-compacted-1")
    token = set_publish_session(session)
    try:
        receipt = context_compacted_receipt(
            step=3,
            original_kinds=("generic",),
            kept_kinds=("generic",),
            mode="enforce",
            applied=True,
        )
        result = commit_memory_journal_receipt(receipt)
        assert result is not None
        event = session.event_at(0)
        assert event is not None
        assert event.type == "context.compacted.v1"
        assert event.data["step"] == 3
        assert event.data["mode"] == "enforce"
        assert event.data["applied"] is True
    finally:
        reset_publish_session(token)


def test_commit_memory_read_spine_receipt() -> None:
    session = Session("t-memory-read-1")
    token = set_publish_session(session)
    try:
        receipt = memory_read_spine_receipt(state_id="trace-abc")
        result = commit_memory_spine_receipt(receipt)
        assert result is not None
        assert session.event_count == 1
        event = session.event_at(0)
        assert event is not None
        assert event.type == "spine.cognition.memory.read"
        assert event.data["payload"]["state_id"] == "trace-abc"
    finally:
        reset_publish_session(token)


def test_commit_memory_spine_receipt_noop_when_unbound() -> None:
    receipt = MemorySpineReceipt(ep="memory.read", payload={"state_id": "x"})
    assert commit_memory_spine_receipt(receipt) is None
