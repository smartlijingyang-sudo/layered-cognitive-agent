"""Coding Agent Tools bundle plugin —— ADR-0065 §六 / PR-8。

注册 7 个只读 tool 到各自 capability;**不允许 journal.write**。
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.observability.coding_agent_tools import (
    DiffContextTool,
    FailureExplainerTool,
    MinimalReproductionTool,
    OptimizationFinderTool,
    PluginGraphRendererTool,
    RunDiffTool,
    TraceInspectorTool,
)
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
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
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("context.read",),
        evidence=("lca-coding-agent-tools-bundle.checked", "lca-coding-agent-tools-bundle.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(
            "coding_agent_diff_context",
            "coding_agent_failure_explainer",
            "coding_agent_minimal_reproduction",
            "coding_agent_optimization_finder",
            "coding_agent_plugin_graph_renderer",
            "coding_agent_run_diff",
            "coding_agent_trace_inspector",
        ),
        emits=(
            "coding_agent_trace_inspector.checked",
            "coding_agent_failure_explainer.checked",
            "coding_agent_optimization_finder.checked",
            "coding_agent_plugin_graph_renderer.checked",
            "coding_agent_minimal_reproduction.checked",
            "coding_agent_diff_context.checked",
            "coding_agent_run_diff.checked",
        ),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.tools.diagnostics.diff_context import (
        DiffContext,
    )
    from lca.plugins.tools.diagnostics.failure_explainer import (
        FailureExplainer,
    )
    from lca.plugins.tools.diagnostics.minimal_reproduction import (
        MinimalReproduction,
    )
    from lca.plugins.tools.diagnostics.optimization_finder import (
        OptimizationFinder,
    )
    from lca.plugins.tools.diagnostics.plugin_graph_renderer import (
        PluginGraphRenderer,
    )
    from lca.plugins.tools.diagnostics.run_diff import (
        RunDiffToolAdapter,
    )
    from lca.plugins.tools.diagnostics.trace_inspector_tool import (
        TraceInspectorToolAdapter,
    )

    jsonl_path = Path(config.jsonl_path)
    trace_inspector = TraceInspectorToolAdapter(jsonl_path)
    failure_explainer = FailureExplainer(jsonl_path)
    optimization_finder = OptimizationFinder(jsonl_path)
    plugin_graph_renderer = PluginGraphRenderer(jsonl_path)
    minimal_reproduction = MinimalReproduction(jsonl_path)
    diff_context = DiffContext(jsonl_path)
    run_diff = RunDiffToolAdapter(jsonl_path)
    ctx.provide("coding_agent_trace_inspector", trace_inspector)
    ctx.provide("coding_agent_failure_explainer", failure_explainer)
    ctx.provide("coding_agent_optimization_finder", optimization_finder)
    ctx.provide("coding_agent_plugin_graph_renderer", plugin_graph_renderer)
    ctx.provide("coding_agent_minimal_reproduction", minimal_reproduction)
    ctx.provide("coding_agent_diff_context", diff_context)
    ctx.provide("coding_agent_run_diff", run_diff)
