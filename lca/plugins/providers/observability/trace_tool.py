"""TraceInspector tools factory plugin (Tier-2) —— ADR-0063 PR-9.

把 5 个 ``TraceTool`` 注册到 ``trace_inspector_tools`` seam：

- ``inspect-trace`` → TraceInspector.inspect_trace
- ``explain-failure`` → TraceInspector.explain_failure
- ``find-optimization-candidates`` → TraceInspector.find_optimization_candidates
- ``export-minimal-reproduction`` → TraceInspector.export_minimal_reproduction
- ``plugin-interaction-graph`` → TraceInspector.plugin_interaction_graph

新增工具 = 一个工厂 + 注册一行；不改 ``BoundObservability`` 装配。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.trace_tool import TraceTool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-trace-tool-provider",
    requires=["trace_inspector_tools"],
    implements=[TraceTool],
    layer="L3",
    effects="none",
    description="Register 5 TraceInspector tools (PR-9).",
    test_suite="tests/test_trace_tool.py::test_provider_registers_all_tools",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-trace-tool-provider.checked', 'lca-trace-tool-provider.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import (
        make_explain_failure_tool,
        make_export_minimal_reproduction_tool,
        make_find_optimization_tool,
        make_inspect_trace_tool,
        make_plugin_interaction_graph_tool,
    )

    tools = {
        "inspect-trace": make_inspect_trace_tool(),
        "explain-failure": make_explain_failure_tool(),
        "find-optimization-candidates": make_find_optimization_tool(),
        "export-minimal-reproduction": make_export_minimal_reproduction_tool(),
        "plugin-interaction-graph": make_plugin_interaction_graph_tool(),
    }
    from lca.infrastructure.observability import NamedRegistry

    tools_map: NamedRegistry = ctx.require("trace_inspector_tools")
    for name, tool in tools.items():
        tools_map.register(name, tool)
    ctx.register("trace_inspector_tools", "tools", tools_map)
