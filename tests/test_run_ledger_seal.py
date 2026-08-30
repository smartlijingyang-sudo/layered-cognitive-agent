"""RunLedger L7 终态封存(ADR-0065 PR-4 / L7)。

- terminal event(AgentRunFinished / TeamRunFinished)提交后 is_sealed=True
- sealed 后 append 抛 LedgerSealedError
- seal() 等价于 append(terminal_event)
- stats() 报告正确 run_seq / is_sealed
- 不在临界区外的 publish;terminal 在临界区内 publish + seal
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    LlmCallCompleted,
    StampedEvent,
    TeamRunFinished,
)
from lca.contracts.observability.ledger import LedgerSealedError, RunLedger
from lca.infrastructure.observability.journal.engine.engine import RunStore


def test_run_store_satisfies_run_ledger_protocol() -> None:
    """RunStore 满足 RunLedger Protocol(runtime_checkable)。"""
    store: RunLedger = RunStore(run_id="r1")
    assert isinstance(store, RunLedger)


def test_terminal_event_seals_ledger() -> None:
    """L7: terminal event 经 ``seal()`` 显式提交后 is_sealed=True。

    append() 不再自动 seal(team shared-store 兼容);seal() 是显式入口。
    """
    store = RunStore(run_id="r1")
    assert store.is_sealed is False
    finished = AgentRunFinished(status="completed")
    store.append(finished)
    # append 不自动 seal
    assert store.is_sealed is False
    # seal() 显式封存
    store.seal(finished)
    assert store.is_sealed is True
    assert store.run_seq == 2  # 1 from append + 1 from seal (terminal event appended again)


def test_seal_method_equivalent_to_append_terminal() -> None:
    store = RunStore(run_id="r1")
    store.seal(AgentRunFinished(status="completed"))
    assert store.is_sealed is True
    assert store.run_seq == 1


def test_append_after_seal_raises() -> None:
    store = RunStore(run_id="r1")
    store.seal(AgentRunFinished(status="completed"))
    with pytest.raises(LedgerSealedError):
        store.append(AgentRunStarted(agent_role="researcher"))


def test_team_finished_does_not_seal_agent_ledger() -> None:
    """L7: TeamRunFinished 在单 ledger 模式下不冻结;由 ``seal()`` 显式封存。

    详见 ``engine.py:_TERMINAL_EVENT_TYPES`` 注释;team ledger 拆分是后续 PR。
    """
    store = RunStore(run_id="r1")
    store.append(TeamRunFinished(status="completed"))
    assert store.is_sealed is False
    # 显式 seal() 触发封存
    store.seal(AgentRunFinished(status="completed"))
    assert store.is_sealed is True


def test_non_terminal_event_does_not_seal() -> None:
    store = RunStore(run_id="r1")
    store.append(AgentRunStarted(agent_role="researcher"))
    store.append(LlmCallCompleted(model="test", ok=True))
    assert store.is_sealed is False
    assert store.run_seq == 2


def test_seal_idempotent_when_already_sealed() -> None:
    store = RunStore(run_id="r1")
    store.seal(AgentRunFinished(status="completed"))
    # 再次 seal 抛错(L7: 已封存)
    with pytest.raises(LedgerSealedError):
        store.seal(AgentRunFinished(status="failed"))


def test_stats_reports_correct_run_seq_and_seal() -> None:
    store = RunStore(run_id="r-stats")
    for _ in range(5):
        store.append(AgentRunStarted(agent_role="a"))
    assert store.stats().run_seq == 5
    assert store.stats().is_sealed is False
    assert store.stats().run_id == "r-stats"
    store.seal(AgentRunFinished(status="completed"))
    stats = store.stats()
    assert stats.is_sealed is True
    assert stats.run_seq == 6


def test_sealed_ledger_still_returns_events() -> None:
    """L7: 封存后 get/events 仍可读;只拒绝追加。"""
    store = RunStore(run_id="r1")
    store.append(AgentRunStarted(agent_role="a"))
    store.seal(AgentRunFinished(status="completed"))
    events: Sequence[StampedEvent] = store.events
    assert len(events) == 2
    assert store.get(1) is not None
    assert store.get(2) is not None
    assert store.get(3) is None


def test_close_after_seal_is_safe() -> None:
    store = RunStore(run_id="r1")
    store.seal(AgentRunFinished(status="completed"))
    store.close()
    # 二次 close 安全
    store.close()


def test_flush_after_seal_is_safe() -> None:
    store = RunStore(run_id="r1")
    store.seal(AgentRunFinished(status="completed"))
    store.flush()  # 不抛错
