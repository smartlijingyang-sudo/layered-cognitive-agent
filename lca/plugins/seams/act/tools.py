"""Tools Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-tools-service",
    provides=["tools"],
    requires=[],
    implements=["ToolRegistry"],
    layer="L0",
    effects="tools",
    description="Provide the Tool registry Definition service (forked per-run).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("tool.invoke",),
        evidence=("lca-tools-service.checked", "lca-tools-service.served"),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("tool.invoke", "tools"),
        emits=("tools.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.tools import ToolsService

    ctx.provide("tools", ToolsService())
