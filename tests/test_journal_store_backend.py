"""JournalStoreBackend 行为测试（ADR-0063 PR-8）。"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    InboxFollowupCreated,
    RunScope,
    StampedEvent,
)
from lca.contracts.observability.journal_store import JournalStoreBackend
from lca.infrastructure.observability import (
    InMemoryJournalStore,
    RunStore,
)


def _scope() -> RunScope:
    return RunScope(trace_id="t", run_id="r")


def test_in_memory_backend_implements_protocol() -> None:
    """InMemoryJournalStore 必须满足 JournalStoreBackend Protocol。"""
    backend = InMemoryJournalStore()
    assert isinstance(backend, JournalStoreBackend)


def test_append_assigns_seq_in_caller() -> None:
    """backend 仅追加；seq 由 caller 在构造 StampedEvent 时分配。"""
    backend = InMemoryJournalStore()
    stamped = StampedEvent(
        seq=1,
        ts=1000.0,
        scope=_scope(),
        event=AgentRunStarted(agent_role="tester"),
    )
    returned = backend.append(stamped)
    assert returned is stamped
    assert backend.get(1) is stamped


def test_get_out_of_range_returns_none() -> None:
    backend = InMemoryJournalStore()
    assert backend.get(0) is None
    assert backend.get(1) is None
    assert backend.get(-1) is None


def test_read_from_filters_correctly() -> None:
    backend = InMemoryJournalStore()
    for seq in range(1, 4):
        stamped = StampedEvent(
            seq=seq,
            ts=1000.0 + seq,
            scope=_scope(),
            event=InboxFollowupCreated(inbox_id=f"i{seq}"),
        )
        backend.append(stamped)
    after_two = backend.read_from(2)
    assert [s.seq for s in after_two] == [3]


def test_events_returns_independent_tuple() -> None:
    """events() 每次返回新 tuple，互不影响。"""
    backend = InMemoryJournalStore()
    backend.append(
        StampedEvent(seq=1, ts=1.0, scope=_scope(), event=AgentRunStarted(agent_role="x"))
    )
    snapshot_a = backend.events()
    backend.append(
        StampedEvent(
            seq=2,
            ts=2.0,
            scope=_scope(),
            event=AgentRunFinished(status="completed"),
        )
    )
    snapshot_b = backend.events()
    assert len(snapshot_a) == 1
    assert len(snapshot_b) == 2


def test_run_store_uses_default_in_memory_backend() -> None:
    """RunStore() 默认 backend 是 InMemoryJournalStore，行为 100% 等价。"""
    store = RunStore()
    assert isinstance(store.backend, InMemoryJournalStore)
    stamped = store.append(InboxFollowupCreated(inbox_id="i", actor="u", target="t", priority="p"))
    assert store.events == (stamped,)
    assert store.get(1) is stamped
    assert store.read_from(0) == (stamped,)
    assert store.seq == 1


def test_run_store_accepts_explicit_backend() -> None:
    backend = InMemoryJournalStore()
    store = RunStore(backend=backend)
    assert store.backend is backend


def test_seam_provides_journal_store() -> None:
    """seam plugin 模块可导入。"""
    from lca.plugins.seam_definitions import journal_store_factories as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-journal-store-factory-registry"


def test_provider_registers_memory_factory() -> None:
    """provider plugin 模块可导入并暴露 memory factory。"""
    from lca.plugins import providers  # noqa: F401
    from lca.plugins.providers import fact_store_memory as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-fact-store-memory-factory"
