"""轨迹分析守卫：规则是纯函数，账本洞察必须只读派生。"""

from __future__ import annotations

from lca.contracts.models.observability.event import OperationOutcome, RuntimeKind
from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    LlmCallCompleted,
    RunScope,
    RuntimeObserved,
    ToolInvoked,
    run_scope,
)
from lca.layer0_infra.observability import ObservabilityHub, TraceInspector, bind, record
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
        actions={"r1": ["delegate", "delegate", "delegate"]}, runs={"r1": {"role": "Lead"}}
    )
    found = rules.detect_loop(summary)
    assert len(found) == 1
    assert "Lead" in found[0][1] and "循环" in found[0][1]


def test_no_loop_for_varied_actions() -> None:
    summary = _summary(actions={"r1": ["delegate", "respond", "delegate"]})
    assert rules.detect_loop(summary) == []


def test_no_loop_for_normal_lead_delegation_pattern() -> None:
    summary = _summary(
        actions={"r1": ["delegate", "respond", "delegate", "respond", "delegate"]},
        runs={"r1": {"role": "Lead"}},
    )
    assert rules.detect_loop(summary) == []


def test_no_loop_for_different_tools() -> None:
    summary = _summary(
        actions={"r1": ["use_tool(calculator)", "use_tool(search)", "use_tool(read_file)"]},
        runs={"r1": {"role": "独立分析师"}},
    )
    assert rules.detect_loop(summary) == []


def test_loop_detected_on_same_tool_repeated() -> None:
    summary = _summary(
        actions={"r1": ["use_tool(calculator)", "use_tool(calculator)", "use_tool(calculator)"]},
        runs={"r1": {"role": "独立分析师"}},
    )
    found = rules.detect_loop(summary)
    assert len(found) == 1
    assert "use_tool(calculator)" in found[0][1]


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
    kinds = {kind for kind, _, _ in rules.run_all_rules(summary)}
    assert rules.INSIGHT_REDUNDANT_TOOL in kinds
    assert rules.INSIGHT_CRITICAL_PATH in kinds
    assert rules.INSIGHT_COST in kinds


# ── 账本只读轨迹检查 ─────────────────────────────────────


def test_trace_inspector_finds_bottleneck_without_writing_insight_events() -> None:
    hub = ObservabilityHub([])
    try:
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r", agent_role="商务经理")):
            record(AgentRunStarted(agent_role="商务经理", objective="谈价"))
            record(
                ToolInvoked(
                    tool_name="calculator", arguments_preview="2400000 * 0.2", latency_ms=12
                )
            )
            record(LlmCallCompleted(model="m", latency_ms=40, prompt_tokens=5, completion_tokens=3))
            record(AgentRunFinished(status="completed", steps=2))
        inspector = TraceInspector(hub.store.events)
        report = inspector.inspect_trace(trace_id="t", focus="latency")
        assert report.bottlenecks[0]["name"] == "m"
        assert all(event.event_type != "RunInsight" for event in hub.store.events)
    finally:
        hub.close()


def test_trace_inspector_explains_failure_through_parent_seq() -> None:
    hub = ObservabilityHub([])
    try:
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r", agent_role="coder")):
            source = hub.store.append(
                RuntimeObserved(
                    kind=RuntimeKind.PLUGIN,
                    operation="plugin.interaction",
                    source="router",
                    attributes={"target_plugin": "sandbox"},
                )
            )
            failure = hub.store.append(
                RuntimeObserved(
                    kind=RuntimeKind.CODE,
                    operation="code.execution",
                    source="sandbox",
                    outcome=OperationOutcome.ERROR,
                    error_code="exit_1",
                    error_message="command failed",
                    causation_refs=(source.seq,),
                )
            )
        report = TraceInspector(hub.store.events).explain_failure(trace_id="t")
        assert report.causal_chain == (source.seq, failure.seq)
        assert [event["seq"] for event in report.events][:2] == [source.seq, failure.seq]
        assert '"router" -->|ok| "sandbox"' in report.plugin_graph
    finally:
        hub.close()


def test_trace_inspector_exports_minimal_failure_reproduction() -> None:
    hub = ObservabilityHub([])
    try:
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r")):
            source = hub.store.append(
                RuntimeObserved(operation="context.injected", source="memory")
            )
            hub.store.append(
                RuntimeObserved(
                    kind=RuntimeKind.TOOL,
                    operation="tool.execute",
                    source="shell",
                    outcome=OperationOutcome.ERROR,
                    causation_refs=(source.seq,),
                )
            )
        reproduction = TraceInspector(hub.store.events).export_minimal_reproduction(trace_id="t")
        assert [event["seq"] for event in reproduction] == [1, 2]
    finally:
        hub.close()
