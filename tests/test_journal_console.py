"""journal console 投影守卫 —— 场景卡 / 角色分节 / Run Card / 序列图。

并发交错下叙事行必须落在各自角色的节里（section 由事件 scope 推导，
无状态回退）；Run Card 在根容器关闭时渲染终态汇总。
"""

from __future__ import annotations

import io

import pytest

from lca.contracts.journal import (
    AgentRunFinished,
    AgentRunStarted,
    DelegationCompleted,
    DelegationIssued,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    TeamRunFinished,
    TeamRunStarted,
    ToolInvoked,
)
from lca.layer0_infra.observability.journal.console_projector import ConsoleJournalProjector
from lca.layer0_infra.observability.policy import Verbosity

_BASE_TS = 2_000_000.0


def _stamped(seq: int, ts: float, scope: RunScope, event: object) -> StampedEvent:
    return StampedEvent(seq=seq, ts=ts, scope=scope, event=event)  # type: ignore[arg-type]


def _feed(projector: ConsoleJournalProjector) -> None:
    """剧本：team(board) → lead 咨询 Alice/Bob（交错）→ 收口。"""
    team_scope = RunScope(trace_id="t", run_id="team-run")
    lead_scope = RunScope(
        trace_id="t", run_id="lead-run", parent_run_id="team-run", agent_role="Lead"
    )
    alice_scope = RunScope(
        trace_id="t",
        run_id="alice-run",
        parent_run_id="lead-run",
        delegation_id="d-a",
        agent_role="Alice",
    )
    bob_scope = RunScope(
        trace_id="t",
        run_id="bob-run",
        parent_run_id="lead-run",
        delegation_id="d-b",
        agent_role="Bob",
    )
    seq = 0

    def emit(ts: float, scope: RunScope, event: object) -> None:
        nonlocal seq
        seq += 1
        projector.on_event(_stamped(seq, ts, scope, event))

    emit(
        _BASE_TS,
        team_scope,
        TeamRunStarted(
            team_id="team-lead",
            strategy_key="lead",
            mandate="board",
            lead_role="Lead",
            members=("Alice", "Bob"),
            objective_preview="目标",
            plan_steps="咨询 | 收口",
        ),
    )
    emit(_BASE_TS + 0.1, lead_scope, AgentRunStarted(agent_role="Lead", objective="目标"))
    emit(
        _BASE_TS + 0.2,
        lead_scope,
        DelegationIssued(
            delegation_id="d-a", caller_role="Lead", callee_role="Alice", subtask_preview="问Alice"
        ),
    )
    emit(
        _BASE_TS + 0.2,
        lead_scope,
        DelegationIssued(
            delegation_id="d-b", caller_role="Lead", callee_role="Bob", subtask_preview="问Bob"
        ),
    )
    emit(_BASE_TS + 0.3, alice_scope, AgentRunStarted(agent_role="Alice", objective="问Alice"))
    emit(_BASE_TS + 0.3, bob_scope, AgentRunStarted(agent_role="Bob", objective="问Bob"))
    # 交错：Bob 的 LLM 先到，再到 Alice
    emit(_BASE_TS + 1.0, bob_scope, LlmCallCompleted(model="m-bob", latency_ms=700))
    emit(_BASE_TS + 1.2, alice_scope, LlmCallCompleted(model="m-alice", latency_ms=900))
    emit(_BASE_TS + 1.3, bob_scope, ToolInvoked(tool_name="calculator", latency_ms=1))
    emit(_BASE_TS + 1.4, alice_scope, AgentRunFinished(status="completed", steps=1))
    emit(
        _BASE_TS + 1.4,
        lead_scope,
        DelegationCompleted(delegation_id="d-a", ok=True, status="completed"),
    )
    emit(_BASE_TS + 1.5, bob_scope, AgentRunFinished(status="completed", steps=2))
    emit(
        _BASE_TS + 1.5,
        lead_scope,
        DelegationCompleted(delegation_id="d-b", ok=True, status="completed"),
    )
    emit(_BASE_TS + 3.0, lead_scope, LlmCallCompleted(model="m-lead", latency_ms=1500))
    emit(_BASE_TS + 3.1, lead_scope, AgentRunFinished(status="completed", steps=2))
    emit(_BASE_TS + 3.2, team_scope, TeamRunFinished(status="completed", steps=5))


# ── 场景卡与 Run Card ───────────────────────────────────


def test_scenario_card_rendered() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(stream=buf)
    _feed(projector)
    out = buf.getvalue()
    assert "run plan" in out
    assert "team-lead" in out and "board" in out
    assert "Alice, Bob" in out
    assert "咨询 | 收口" in out


def test_run_card_rendered_on_team_finish() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(stream=buf)
    _feed(projector)
    out = buf.getvalue()
    assert "run card" in out
    assert "completed" in out
    assert "Lead ✓" in out and "Alice ✓" in out and "Bob ✓" in out
    assert "llm 3 calls" in out
    assert "tool 1 calls" in out


def test_solo_run_card() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(stream=buf)
    scope = RunScope(trace_id="t", run_id="r")
    projector.on_event(
        _stamped(
            1,
            _BASE_TS,
            scope,
            AgentRunStarted(agent_role="Solo", strategy_key="solo", objective="hi"),
        )
    )
    projector.on_event(_stamped(2, _BASE_TS + 1, scope, LlmCallCompleted(model="m", latency_ms=10)))
    projector.on_event(
        _stamped(3, _BASE_TS + 1, scope, AgentRunFinished(status="completed", steps=1))
    )
    out = buf.getvalue()
    assert "run card" in out and "Solo ✓" in out


# ── 角色分节（并发交错）────────────────────────────────


def _sections(out: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith("── ") and "─" in line[3:]:
            current = line.strip("─ \n")
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return sections


def test_interleaved_events_land_in_correct_sections() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(stream=buf)
    _feed(projector)
    sections = _sections(buf.getvalue())
    alice_block = "\n".join(sections.get("Alice", []))
    bob_block = "\n".join(sections.get("Bob", []))
    assert "m-alice" in alice_block and "m-bob" not in alice_block
    assert "m-bob" in bob_block and "m-alice" not in bob_block
    assert "calculator" in bob_block


def test_delegation_narrative_lines() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(stream=buf)
    _feed(projector)
    out = buf.getvalue()
    assert "⇢ Alice: 问Alice" in out
    assert "⇠ Alice completed" in out


# ── verbosity 分档 ─────────────────────────────────────


def test_minimal_only_cards() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(Verbosity.MINIMAL, stream=buf)
    _feed(projector)
    out = buf.getvalue()
    assert "run plan" in out and "run card" in out
    assert "llm.chat" not in out  # 叙事行被抑制


def test_verbose_includes_sequence_diagram() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(Verbosity.VERBOSE, stream=buf)
    _feed(projector)
    out = buf.getvalue()
    assert "sequenceDiagram" in out
    assert "Lead->>Alice" in out
    assert "Alice-->>Lead" in out


def test_no_diagram_without_delegation() -> None:
    buf = io.StringIO()
    projector = ConsoleJournalProjector(Verbosity.VERBOSE, stream=buf)
    scope = RunScope(trace_id="t", run_id="r")
    projector.on_event(
        _stamped(1, _BASE_TS, scope, AgentRunStarted(agent_role="Solo", objective="hi"))
    )
    projector.on_event(_stamped(2, _BASE_TS + 1, scope, AgentRunFinished(status="completed")))
    assert "sequenceDiagram" not in buf.getvalue()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
