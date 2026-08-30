"""TraceInspector 工具注册测试（ADR-0063 PR-9）。"""

from __future__ import annotations

from lca.contracts.models.observability.journal import (
    AgentRunFinished,
    AgentRunStarted,
    LlmCallCompleted,
    RunScope,
    StampedEvent,
    ToolInvoked,
)
from lca.infrastructure.observability.trace_inspector import TraceInspector
from lca.infrastructure.observability.trace_tool_runner import (
    make_explain_failure_tool,
    make_export_minimal_reproduction_tool,
    make_find_optimization_tool,
    make_inspect_trace_tool,
    make_plugin_interaction_graph_tool,
)


def _scope() -> RunScope:
    return RunScope(trace_id="t", run_id="r")


def _stamped(seq: int, event: object, *, ts: float = 1000.0) -> StampedEvent:
    return StampedEvent(  # type: ignore[arg-type]
        seq=seq, ts=ts, scope=_scope(), event=event
    )


def test_all_five_tools_have_unique_names() -> None:
    tools = [
        make_inspect_trace_tool(),
        make_explain_failure_tool(),
        make_find_optimization_tool(),
        make_export_minimal_reproduction_tool(),
        make_plugin_interaction_graph_tool(),
    ]
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names))
    assert "inspect-trace" in names
    assert "explain-failure" in names


def test_inspect_trace_tool_matches_inspector() -> None:
    events = (
        _stamped(1, AgentRunStarted(agent_role="tester")),
        _stamped(2, AgentRunFinished(status="completed")),
    )
    inspector = TraceInspector(events)
    direct = inspector.inspect_trace().summary
    via_tool = make_inspect_trace_tool().invoke(events=events)
    assert via_tool["summary"] == direct


def test_explain_failure_tool_returns_empty_when_no_failure() -> None:
    events = (_stamped(1, AgentRunStarted(agent_role="tester")),)
    result = make_explain_failure_tool().invoke(events=events)
    assert result["event_count"] == 1
    assert "未在所选事件中发现失败" in result["summary"]


def test_find_optimization_tool_sorts_by_duration() -> None:
    events = (
        _stamped(1, LlmCallCompleted(model="m", latency_ms=100)),
        _stamped(2, LlmCallCompleted(model="m", latency_ms=500)),
        _stamped(3, ToolInvoked(tool_name="t", latency_ms=200)),
    )
    result = make_find_optimization_tool().invoke(events=events, limit=5)
    durations = [c["duration_ms"] for c in result["candidates"]]
    assert durations == sorted(durations, reverse=True)


def test_export_minimal_reproduction_returns_subset() -> None:
    events = (
        _stamped(1, AgentRunStarted(agent_role="tester")),
        _stamped(2, AgentRunFinished(status="error", error="boom")),
    )
    result = make_export_minimal_reproduction_tool().invoke(events=events)
    assert "events" in result
    assert len(result["events"]) <= 2


def test_plugin_interaction_graph_default_empty() -> None:
    events = (_stamped(1, AgentRunStarted(agent_role="x")),)
    result = make_plugin_interaction_graph_tool().invoke(events=events)
    assert "mermaid" in result
    assert "Empty" in result["mermaid"]


def test_seam_provides_tools() -> None:
    from lca.plugins.seam_definitions.observability import trace_tool as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-trace-tool-seam"


def test_provider_registers_all_tools() -> None:
    from lca.plugins import providers  # noqa: F401
    from lca.plugins.providers import trace_tool as mod

    assert hasattr(mod, "setup")
    meta = getattr(mod.setup, "meta", {})
    assert meta.get("id") == "lca-trace-tool-provider"
