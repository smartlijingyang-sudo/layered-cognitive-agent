"""TraceTool 工厂（ADR-0063 PR-9）。

把 ``TraceInspector`` 的 5 个方法包装为 ``TraceTool``，注册到 ``tools`` seam。
新增工具 = 写一个工厂 + 注册一行。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

from lca.contracts.models.observability.journal import StampedEvent
from lca.contracts.observability.trace_tool import TraceTool
from lca.layer0_infra.observability.trace_inspector import TraceFocus, TraceInspector


def _resolve_events(events: Sequence[StampedEvent] | None) -> Sequence[StampedEvent]:
    return events if events is not None else ()


class _InspectTraceTool:
    name = "inspect-trace"
    description = "返回 trace 的因果链 / 瓶颈 / 插件交互图。focus 支持 all/error/latency/tool/plugin。"

    def invoke(
        self,
        *,
        events: Sequence[StampedEvent] | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        focus: TraceFocus = "all",
        depth: int = 24,
        **kwargs: Any,
    ) -> dict[str, Any]:
        inspector = TraceInspector(_resolve_events(events))
        report = inspector.inspect_trace(
            trace_id=trace_id, run_id=run_id, focus=focus, depth=depth
        )
        return asdict(report)


class _ExplainFailureTool:
    name = "explain-failure"
    description = "返回首个失败的因果祖先 + 同 run 窗口。"

    def invoke(
        self,
        *,
        events: Sequence[StampedEvent] | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        depth: int = 24,
        **kwargs: Any,
    ) -> dict[str, Any]:
        inspector = TraceInspector(_resolve_events(events))
        report = inspector.explain_failure(trace_id=trace_id, run_id=run_id, depth=depth)
        return asdict(report)


class _FindOptimizationTool:
    name = "find-optimization-candidates"
    description = "按延迟排序返回 LLM / 工具 / 插件 / 解释的瓶颈候选。"

    def invoke(
        self,
        *,
        events: Sequence[StampedEvent] | None = None,
        limit: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        inspector = TraceInspector(_resolve_events(events))
        return {
            "candidates": inspector.find_optimization_candidates(limit=limit),
        }


class _ExportMinimalReproductionTool:
    name = "export-minimal-reproduction"
    description = "返回失败事件及其因果祖先的最小封套子集（脱机复现 / 差分 / issue 附件）。"

    def invoke(
        self,
        *,
        events: Sequence[StampedEvent] | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        inspector = TraceInspector(_resolve_events(events))
        return {
            "events": list(
                inspector.export_minimal_reproduction(trace_id=trace_id, run_id=run_id)
            )
        }


class _PluginInteractionGraphTool:
    name = "plugin-interaction-graph"
    description = "返回 RuntimeObserved.plugin.interaction 事件的 Mermaid flowchart。"

    def invoke(
        self,
        *,
        events: Sequence[StampedEvent] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        inspector = TraceInspector(_resolve_events(events))
        return {"mermaid": inspector.plugin_interaction_graph()}


def make_inspect_trace_tool() -> TraceTool:
    return _InspectTraceTool()  # type: ignore[return-value]


def make_explain_failure_tool() -> TraceTool:
    return _ExplainFailureTool()  # type: ignore[return-value]


def make_find_optimization_tool() -> TraceTool:
    return _FindOptimizationTool()  # type: ignore[return-value]


def make_export_minimal_reproduction_tool() -> TraceTool:
    return _ExportMinimalReproductionTool()  # type: ignore[return-value]


def make_plugin_interaction_graph_tool() -> TraceTool:
    return _PluginInteractionGraphTool()  # type: ignore[return-value]


__all__ = [
    "make_explain_failure_tool",
    "make_export_minimal_reproduction_tool",
    "make_find_optimization_tool",
    "make_inspect_trace_tool",
    "make_plugin_interaction_graph_tool",
]