"""TraceInspector tools seam plugin (Tier-1) —— ADR-0063 PR-9.

声明 ``trace_inspector_tools`` 服务形状；boot 后 ``providers/trace_tool`` 注册 5 个
``TraceTool`` 实现（inspect-trace / explain-failure / find-optimization-candidates /
export-minimal-reproduction / plugin-interaction-graph）。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.observability.trace_tool import TraceTool
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-trace-tool-seam",
    provides=["trace_inspector_tools"],
    implements=[TraceTool],
    layer="L3",
    effects="none",
    description="Provide the TraceInspector tools seam (PR-9).",
    test_suite="tests/test_trace_tool.py::test_seam_provides_tools",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('tool.invoke',),
        evidence=('lca-trace-tool-seam.checked', 'lca-trace-tool-seam.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('tool.invoke', 'trace_inspector_tools'),
        emits=('trace_inspector_tools.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.observability import NamedRegistry

    ctx.provide("trace_inspector_tools", NamedRegistry())
