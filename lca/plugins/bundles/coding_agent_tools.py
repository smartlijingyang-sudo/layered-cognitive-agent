"""Coding Agent Tools bundle plugin —— ADR-0065 §六 / PR-8。

注册 7 个只读 tool 到各自 capability;**不允许 journal.write**。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.coding_agent_tools import (
    DiffContextTool,
    FailureExplainerTool,
    MinimalReproductionTool,
    OptimizationFinderTool,
    PluginGraphRendererTool,
    RunDiffTool,
    TraceInspectorTool,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jsonl_path: str = "traces/lca_journal.jsonl"


@plugin(
    id="lca-coding-agent-tools-bundle",
    provides=[
        "coding_agent_trace_inspector",
        "coding_agent_failure_explainer",
        "coding_agent_optimization_finder",
        "coding_agent_plugin_graph_renderer",
        "coding_agent_minimal_reproduction",
        "coding_agent_diff_context",
        "coding_agent_run_diff",
    ],
    implements=[
        TraceInspectorTool,
        FailureExplainerTool,
        OptimizationFinderTool,
        PluginGraphRendererTool,
        MinimalReproductionTool,
        DiffContextTool,
        RunDiffTool,
    ],
    layer="L0",
    effects="none",
    description="Coding Agent Tools bundle (7 read-only tools). ADR-0065 §六 / PR-8.",
    test_suite="tests/test_coding_agent_tools_bundle.py::test_bundle_registers_seven_tools",
    kind=PluginKind.BRIDGE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.layer0_infra.observability.coding_agent_tools.diff_context import (
        DiffContext,
    )
    from lca.layer0_infra.observability.coding_agent_tools.failure_explainer import (
        FailureExplainer,
    )
    from lca.layer0_infra.observability.coding_agent_tools.minimal_reproduction import (
        MinimalReproduction,
    )
    from lca.layer0_infra.observability.coding_agent_tools.optimization_finder import (
        OptimizationFinder,
    )
    from lca.layer0_infra.observability.coding_agent_tools.plugin_graph_renderer import (
        PluginGraphRenderer,
    )
    from lca.layer0_infra.observability.coding_agent_tools.run_diff import (
        RunDiffToolImpl,
    )
    from lca.layer0_infra.observability.coding_agent_tools.trace_inspector_tool import (
        TraceInspectorToolImpl,
    )

    jsonl_path = Path(config.jsonl_path)
    trace_inspector = TraceInspectorToolImpl(jsonl_path)
    failure_explainer = FailureExplainer(jsonl_path)
    optimization_finder = OptimizationFinder(jsonl_path)
    plugin_graph_renderer = PluginGraphRenderer(jsonl_path)
    minimal_reproduction = MinimalReproduction(jsonl_path)
    diff_context = DiffContext(jsonl_path)
    run_diff = RunDiffToolImpl(jsonl_path)
    ctx.provide("coding_agent_trace_inspector", trace_inspector)
    ctx.provide("coding_agent_failure_explainer", failure_explainer)
    ctx.provide("coding_agent_optimization_finder", optimization_finder)
    ctx.provide("coding_agent_plugin_graph_renderer", plugin_graph_renderer)
    ctx.provide("coding_agent_minimal_reproduction", minimal_reproduction)
    ctx.provide("coding_agent_diff_context", diff_context)
    ctx.provide("coding_agent_run_diff", run_diff)
