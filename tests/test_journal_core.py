"""执行日志核心引擎守卫（ADR-0037 Stage 0）。

覆盖：关联骨架盖章 / 词表 fail-fast / 写入期策略强制 / 投影器扇出与
故障隔离 / facade record() / RunScope 跨 asyncio.create_task 传播。
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
    get_current_run_scope,
    run_scope,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.layer0_infra.observability import (
    ExecutionJournal,
    ObservabilityHub,
    UnregisteredJournalEventError,
    bind,
    record,
)
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity


class _Collector:
    """测试投影器：按序收集盖章记录。"""

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
    journal = ExecutionJournal()
    scope = RunScope(
        trace_id="trace-1",
        run_id="run-lead",
        parent_run_id="run-team",
        delegation_id="dlg-1",
        agent_role="客户成功总监",
    )
    with run_scope(scope):
        stamped = journal.record(TeamRunStarted(team_id="team-lead"))
    assert stamped.scope == scope
    assert stamped.seq == 1
    assert stamped.ts > 0


def test_record_without_scope_stamps_empty() -> None:
    journal = ExecutionJournal()
    stamped = journal.record(TeamRunStarted(team_id="team-x"))
    assert stamped.scope == RunScope()
    assert stamped.scope.parent_run_id is None


def test_seq_monotonic_and_events_append_only() -> None:
    journal = ExecutionJournal()
    journal.record(TeamRunStarted())
    journal.record(TeamRunStarted())
    seqs = [s.seq for s in journal.events]
    assert seqs == [1, 2]


# ── 词表 fail-fast ───────────────────────────────────────


def test_unregistered_event_raises() -> None:
    class RogueEvent(JournalEvent):
        pass

    with pytest.raises(UnregisteredJournalEventError):
        ExecutionJournal().record(RogueEvent())


def test_catalog_classes_are_constructible_defaults() -> None:
    """词表内所有事件必须可用无参默认构造（发射点一律关键字填域字段）。"""
    for cls_name, cls in JOURNAL_EVENT_CLASSES.items():
        instance = cls()
        assert type(instance).__name__ == cls_name


# ── 写入期策略强制 ───────────────────────────────────────


def test_secret_in_journal_field_redacted_at_record() -> None:
    journal = ExecutionJournal()
    stamped = journal.record(
        LlmCallCompleted(model="stub", prompt_preview="key=sk-1234567890abcdef 正常内容")
    )
    event = stamped.event
    assert isinstance(event, LlmCallCompleted)
    assert "sk-1234567890abcdef" not in event.prompt_preview
    assert "[REDACTED]" in event.prompt_preview


def test_enum_fields_normalized_at_record() -> None:
    """枚举字段（str 混入词表枚举）写入期归一为纯值，杜绝 repr 泄漏。"""
    journal = ExecutionJournal()
    stamped = journal.record(
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
    journal = ExecutionJournal(policy=AttributePolicy(Verbosity.MINIMAL))
    stamped = journal.record(LlmCallCompleted(model="stub", prompt_preview="长" * 5000))
    event = stamped.event
    assert isinstance(event, LlmCallCompleted)
    assert event.prompt_preview == ""


# ── 投影器扇出与故障隔离 ─────────────────────────────────


def test_projectors_receive_events_in_order() -> None:
    collector = _Collector()
    journal = ExecutionJournal([collector])
    journal.record(TeamRunStarted(team_id="a"))
    journal.record(TeamRunStarted(team_id="b"))
    assert [s.event.team_id for s in collector.received] == ["a", "b"]  # type: ignore[attr-defined]


def test_failing_projector_does_not_break_journal() -> None:
    class Exploding:
        def on_event(self, stamped: StampedEvent) -> None:
            raise RuntimeError("boom")

        def flush(self) -> None:
            raise RuntimeError("boom")

        def close(self) -> None:
            raise RuntimeError("boom")

    good = _Collector()
    journal = ExecutionJournal([Exploding(), good])
    stamped = journal.record(TeamRunStarted(team_id="ok"))  # 不被打断
    assert stamped.seq == 1
    assert len(good.received) == 1
    journal.flush()
    journal.close()
    assert good.closed


def test_hub_lifecycle_flushes_and_closes_journal() -> None:
    collector = _Collector()
    hub = ObservabilityHub([], journal_projectors=[collector])
    with bind(hub):
        record(TeamRunStarted(team_id="lifecycle"))
    hub.close()
    assert len(collector.received) == 1
    assert collector.flushed >= 1
    assert collector.closed


# ── facade record() ──────────────────────────────────────


def test_facade_record_routes_through_hub() -> None:
    hub = ObservabilityHub([])
    try:
        with bind(hub), run_scope(RunScope(run_id="r-1")):
            record(TeamRunStarted(team_id="via-facade"))
        assert len(hub.journal.events) == 1
        assert hub.journal.events[0].scope.run_id == "r-1"
    finally:
        hub.close()  # 容器必闭：投影 attach 不泄漏到后续测试


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
