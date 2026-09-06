"""MemoryJournalReceipt commit tests (ADR-0194 P1-13)."""

from __future__ import annotations

from lca.contracts.models.observability.journal import ContextCompacted, MemoryCommitted
from lca.contracts.models.observability.memory_journal_receipt import (
    MemoryJournalReceipt,
    MemorySpineReceipt,
    context_compacted_receipt,
    memory_committed_receipt,
    memory_read_spine_receipt,
)
from lca.loop.memory_journal_commit import (
    commit_memory_journal_receipt,
    commit_memory_spine_receipt,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.plugins.session.runtime.session import Session


def test_commit_memory_journal_receipt_uses_journal_append() -> None:
    from lca.contracts.models.observability.journal import RunScope
    from lca.infrastructure.observability import bind_backends, run_scope
    from tests.support.observability_helpers import make_test_bound

    hub = make_test_bound()
    receipt = memory_committed_receipt(layer="working", record_id="rec-1")
    with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
        stamped = commit_memory_journal_receipt(receipt)
    assert stamped is not None
    assert isinstance(stamped.event, MemoryCommitted)
    assert stamped.event.record_id == "rec-1"


def test_commit_memory_journal_receipt_noop_when_unbound() -> None:
    receipt = MemoryJournalReceipt(
        journal_event=MemoryCommitted(layer="working", record_id="rec-2"),
    )
    assert commit_memory_journal_receipt(receipt) is None


def test_commit_context_compacted_receipt() -> None:
    from lca.contracts.models.observability.journal import RunScope
    from lca.infrastructure.observability import bind_backends, run_scope
    from tests.support.observability_helpers import make_test_bound

    hub = make_test_bound()
    receipt = context_compacted_receipt(
        step=3,
        original_kinds=("generic",),
        kept_kinds=("generic",),
        mode="enforce",
        applied=True,
    )
    with bind_backends(hub), run_scope(RunScope(trace_id="t1", run_id="r1")):
        stamped = commit_memory_journal_receipt(receipt)
    assert stamped is not None
    event = stamped.event
    assert isinstance(event, ContextCompacted)
    assert event.step == 3
    assert event.mode == "enforce"
    assert event.applied is True


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
