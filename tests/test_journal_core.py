"""执行日志核心引擎守卫（ADR-0055 RunStore）。

覆盖：关联骨架盖章 / 词表 fail-fast / 写入期策略强制 / subscriber 扇出与
故障隔离 / facade record() / RunScope 跨 asyncio.create_task 传播 /
commit-before-observe / read_from 自拉。
"""

from __future__ import annotations

import asyncio

import pytest

from lca.contracts.models.observability.journal import (
    DelegationIssued,
    DelegationMechanism,
    JournalEvent,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    TeamRunStarted,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.layer0_infra.observability import (
    RunStore,
    UnregisteredJournalEventError,
    bind_backends,
    get_current_run_scope,
    record,
    run_scope,
)
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from tests.support.observability_helpers import make_test_bound


class _Collector:
    """测试 subscriber：按序收集盖章记录。"""

    def __init__(self) -> None:
        self.received: list[StampedEvent] = []
        self.flushed = 0
        self.closed = False

    def on_event(self, stamped: StampedEvent) -> None:
        self.received.append(stamped)

    def flush(self) -> None:
        self.flushed += 1

    def close(self) -> None:
        self.closed = True


# ── 关联骨架盖章 ─────────────────────────────────────────


def test_record_stamps_ambient_run_scope() -> None:
    store = RunStore()
    scope = RunScope(
        trace_id="trace-1",
        run_id="run-lead",
        parent_run_id="run-team",
        delegation_id="dlg-1",
        agent_role="客户成功总监",
    )
    with run_scope(scope):
        stamped = store.append(TeamRunStarted(team_id="team-lead"))
    assert stamped.scope == scope
    assert stamped.seq == 1
    assert stamped.ts > 0


def test_record_without_scope_stamps_empty() -> None:
    store = RunStore()
    stamped = store.append(TeamRunStarted(team_id="team-x"))
    assert stamped.scope == RunScope()
    assert stamped.scope.parent_run_id is None


def test_seq_monotonic_and_events_append_only() -> None:
    store = RunStore()
    store.append(TeamRunStarted())
    store.append(TeamRunStarted())
    seqs = [s.seq for s in store.events]
    assert seqs == [1, 2]


# ── 词表 fail-fast ───────────────────────────────────────


def test_unregistered_event_raises() -> None:
    class RogueEvent(JournalEvent):
        pass

    with pytest.raises(UnregisteredJournalEventError):
        RunStore().append(RogueEvent())


def test_catalog_classes_are_constructible_defaults() -> None:
    """词表内所有事件必须可用无参默认构造（发射点一律关键字填域字段）。"""
    for cls_name, cls in JOURNAL_EVENT_CLASSES.items():
        instance = cls()
        assert type(instance).__name__ == cls_name


# ── 写入期策略强制 ───────────────────────────────────────


def test_secret_in_journal_field_redacted_at_record() -> None:
    store = RunStore()
    stamped = store.append(
        LlmCallCompleted(model="stub", prompt_preview="key=sk-1234567890abcdef 正常内容")
    )
    event = stamped.event
    assert isinstance(event, LlmCallCompleted)
    assert "sk-1234567890abcdef" not in event.prompt_preview
    assert "[REDACTED]" in event.prompt_preview


def test_enum_fields_normalized_at_record() -> None:
    """枚举字段（str 混入词表枚举）写入期归一为纯值，杜绝 repr 泄漏。"""
    store = RunStore()
    stamped = store.append(
        DelegationIssued(
            delegation_id="dlg-9",
            callee_role="架构师",
            mechanism=DelegationMechanism.DELEGATE,
        )
    )
    event = stamped.event
    assert isinstance(event, DelegationIssued)
    assert event.mechanism == DelegationMechanism.DELEGATE.value
    assert not isinstance(event.mechanism, DelegationMechanism)


def test_minimal_verbosity_drops_previews_in_journal() -> None:
    store = RunStore(policy=AttributePolicy(Verbosity.MINIMAL))
    stamped = store.append(LlmCallCompleted(model="stub", prompt_preview="长" * 5000))
    event = stamped.event
    assert isinstance(event, LlmCallCompleted)
    assert event.prompt_preview == ""


# ── subscriber 扇出与故障隔离 ─────────────────────────────


def test_subscribers_receive_events_in_order() -> None:
    collector = _Collector()
    store = RunStore([collector])
    store.append(TeamRunStarted(team_id="a"))
    store.append(TeamRunStarted(team_id="b"))
    assert [s.event.team_id for s in collector.received] == ["a", "b"]  # type: ignore[attr-defined]


def test_failing_subscriber_does_not_break_store() -> None:
    class Exploding:
        def on_event(self, stamped: StampedEvent) -> None:
            raise RuntimeError("boom")

        def flush(self) -> None:
            raise RuntimeError("boom")

        def close(self) -> None:
            raise RuntimeError("boom")

    good = _Collector()
    store = RunStore([Exploding(), good])
    stamped = store.append(TeamRunStarted(team_id="ok"))  # 不被打断
    assert stamped.seq == 1
    assert len(good.received) == 1
    store.flush()
    store.close()
    assert good.closed


def test_hub_lifecycle_flushes_and_closes_store() -> None:
    collector = _Collector()
    bound = make_test_bound(projections=[collector])
    with bind_backends(bound):
        record(TeamRunStarted(team_id="lifecycle"))
    bound.journal.flush()  # type: ignore[union-attr]
    bound.journal.close()  # type: ignore[union-attr]
    assert len(collector.received) == 1
    assert collector.flushed >= 1
    assert collector.closed


# ── facade record() ──────────────────────────────────────


def test_facade_record_routes_through_hub() -> None:
    bound = make_test_bound()
    try:
        with bind_backends(bound), run_scope(RunScope(run_id="r-1")):
            record(TeamRunStarted(team_id="via-facade"))
        events = bound.journal.store.events  # type: ignore[union-attr]
        assert len(events) == 1
        assert events[0].scope.run_id == "r-1"
    finally:
        bound.journal.close()  # type: ignore[union-attr]


def test_facade_record_noop_without_hub() -> None:
    record(TeamRunStarted(team_id="no-hub"))  # 安全 no-op


# ── RunScope 跨 asyncio.create_task 传播 ─────────────────


async def test_run_scope_propagates_into_created_tasks() -> None:
    """委派穿透的根基：create_task 拷贝 Context，成员任务读到发起方身份。"""
    captured: list[RunScope | None] = []

    async def member() -> None:
        captured.append(get_current_run_scope())

    scope = RunScope(trace_id="t", run_id="lead", delegation_id="dlg-7", agent_role="lead")
    with run_scope(scope):
        task = asyncio.create_task(member())
        await task
    assert captured == [scope]


# ── commit-before-observe（ADR-0055 N1）──────────────────


def test_commit_before_observe_subscriber_sees_committed_event() -> None:
    """subscriber 看到的事件已在 log 中。"""
    store = RunStore()

    class AssertingSubscriber:
        def on_event(self, stamped: StampedEvent) -> None:
            # 此时 store.events 必须已包含该事件
            assert stamped in store.events

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    store._subscribers = [AssertingSubscriber()]
    store.append(TeamRunStarted(team_id="n1-test"))


# ── read_from 自拉 ───────────────────────────────────────


def test_read_from_returns_events_after_seq() -> None:
    store = RunStore()
    store.append(TeamRunStarted(team_id="a"))
    store.append(TeamRunStarted(team_id="b"))
    store.append(TeamRunStarted(team_id="c"))
    tail = store.read_from(1)
    assert len(tail) == 2
    assert tail[0].seq == 2
    assert tail[1].seq == 3


def test_read_from_zero_returns_all() -> None:
    store = RunStore()
    store.append(TeamRunStarted())
    store.append(TeamRunStarted())
    assert len(store.read_from(0)) == 2


# ── RunStore 基本行为 ────────────────────────────────
