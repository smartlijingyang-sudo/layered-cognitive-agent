"""Insight 层守卫（ADR-0037 Stage 4）：规则纯函数 + 引擎回注闭环。"""

from __future__ import annotations

import time

from lca.contracts.journal import (
    AgentRunFinished,
    AgentRunStarted,
    LlmCallCompleted,
    RunInsight,
    RunScope,
    TeamRunFinished,
    TeamRunStarted,
    ToolInvoked,
    run_scope,
)
from lca.layer0_infra.observability import ObservabilityHub, bind, record
from lca.layer0_infra.observability.journal import insight_rules as rules

_BASE = 5_000_000.0


def _summary(**kw: object) -> dict:
    base = {"tool_calls": [], "llm_calls": [], "runs": {}, "actions": {}}
    base.update(kw)
    return base


# ── 规则纯函数 ───────────────────────────────────────────


def test_redundant_tool_call_detected() -> None:
    summary = _summary(
        tool_calls=[
            {"run_id": "r1", "tool_name": "calculator", "arguments": "2400000 * 0.2"},
            {"run_id": "r1", "tool_name": "calculator", "arguments": "2400000 * 0.2"},
        ],
        runs={"r1": {"role": "商务经理"}},
    )
    found = rules.detect_redundant_tool_calls(summary)
    assert len(found) == 1
    kind, message, detail = found[0]
    assert kind == rules.INSIGHT_REDUNDANT_TOOL
    assert "商务经理" in message and "calculator" in message and "×2" in message
    assert "2400000 * 0.2" in detail


def test_single_tool_call_not_flagged() -> None:
    summary = _summary(tool_calls=[{"run_id": "r1", "tool_name": "calculator", "arguments": "1+1"}])
    assert rules.detect_redundant_tool_calls(summary) == []


def test_loop_detected_on_repeated_action() -> None:
    summary = _summary(
        actions={"r1": ["delegate", "delegate", "delegate"]},
        runs={"r1": {"role": "Lead"}},
    )
    found = rules.detect_loop(summary)
    assert len(found) == 1
    assert "Lead" in found[0][1] and "循环" in found[0][1]


def test_no_loop_for_varied_actions() -> None:
    summary = _summary(actions={"r1": ["delegate", "respond", "delegate"]})
    assert rules.detect_loop(summary) == []


def test_critical_path_picks_longest_run() -> None:
    summary = _summary(
        runs={
            "fast": {"role": "A", "start_ts": _BASE, "end_ts": _BASE + 1, "steps": 1},
            "slow": {"role": "B", "start_ts": _BASE, "end_ts": _BASE + 20, "steps": 3},
        }
    )
    found = rules.detect_critical_path(summary)
    assert len(found) == 1
    assert "B" in found[0][1] and "20000ms" in found[0][1]


def test_cost_summary_aggregates_tokens() -> None:
    summary = _summary(
        llm_calls=[
            {
                "run_id": "r1",
                "model": "m",
                "latency_ms": 100,
                "prompt_tokens": 10,
                "completion_tokens": 5,
            },
            {
                "run_id": "r1",
                "model": "m",
                "latency_ms": 300,
                "prompt_tokens": 20,
                "completion_tokens": 15,
            },
        ]
    )
    found = rules.summarize_cost(summary)
    assert len(found) == 1
    kind, message, detail = found[0]
    assert kind == rules.INSIGHT_COST
    assert "2 次调用" in message and "30 in" in message and "20 out" in message
    assert "slowest" in detail


def test_run_all_rules_combines() -> None:
    summary = _summary(
        tool_calls=[
            {"run_id": "r1", "tool_name": "t", "arguments": "x"},
            {"run_id": "r1", "tool_name": "t", "arguments": "x"},
        ],
        runs={"r1": {"role": "R", "start_ts": _BASE, "end_ts": _BASE + 5, "steps": 1}},
        llm_calls=[
            {
                "run_id": "r1",
                "model": "m",
                "latency_ms": 50,
                "prompt_tokens": 1,
                "completion_tokens": 1,
            }
        ],
    )
    kinds = {k for k, _, _ in rules.run_all_rules(summary)}
    assert rules.INSIGHT_REDUNDANT_TOOL in kinds
    assert rules.INSIGHT_CRITICAL_PATH in kinds
    assert rules.INSIGHT_COST in kinds


# ── 引擎回注闭环（hub 集成）─────────────────────────────


def test_insights_recorded_on_team_finish() -> None:
    hub = ObservabilityHub([])
    try:
        with bind(hub):
            team_scope = RunScope(trace_id="t", run_id="team-run")
            lead_scope = RunScope(
                trace_id="t", run_id="lead-run", parent_run_id="team-run", agent_role="商务经理"
            )
            with run_scope(team_scope):
                record(TeamRunStarted(team_id="team-x", strategy_key="lead"))
            with run_scope(lead_scope):
                record(AgentRunStarted(agent_role="商务经理", objective="谈价"))
                record(
                    ToolInvoked(
                        tool_name="calculator", arguments_preview="2400000 * 0.2", latency_ms=1
                    )
                )
                record(
                    ToolInvoked(
                        tool_name="calculator", arguments_preview="2400000 * 0.2", latency_ms=1
                    )
                )
                record(
                    LlmCallCompleted(model="m", latency_ms=10, prompt_tokens=5, completion_tokens=3)
                )
                time.sleep(0.01)  # 让 run 有真实时长，critical_path 才成立
                record(AgentRunFinished(status="completed", steps=2))
            with run_scope(team_scope):
                record(TeamRunFinished(status="completed", steps=2))
        insights = [e.event for e in hub.journal.events if isinstance(e.event, RunInsight)]
        kinds = {i.kind for i in insights}
        assert rules.INSIGHT_REDUNDANT_TOOL in kinds
        assert rules.INSIGHT_CRITICAL_PATH in kinds
        assert rules.INSIGHT_COST in kinds
    finally:
        hub.close()


def test_insights_not_double_emitted_for_member_runs() -> None:
    """成员 run 收尾不触发洞察（只在根收尾触发一次）。"""
    hub = ObservabilityHub([])
    try:
        with bind(hub):
            member_scope = RunScope(
                trace_id="t",
                run_id="m-run",
                parent_run_id="lead-run",
                delegation_id="d",
                agent_role="A",
            )
            with run_scope(member_scope):
                record(AgentRunStarted(agent_role="A", objective="x"))
                record(AgentRunFinished(status="completed", steps=1))
        insights = [e.event for e in hub.journal.events if isinstance(e.event, RunInsight)]
        assert insights == []
    finally:
        hub.close()
