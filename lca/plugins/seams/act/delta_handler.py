"""DeltaHandlerRegistry Seam Definition plugin — Tier-1."""

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
    id="lca-delta-handler-registry-seam",
    provides=["delta_handler_registry"],
    requires=[],
    implements=["DeltaHandlerRegistry"],
    layer="L2",
    effects="none",
    kind=PluginKind.SEAM,
    description="Provide the DeltaHandlerRegistry Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=(
            "lca-delta-handler-registry-seam.checked",
            "lca-delta-handler-registry-seam.served",
        ),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("delta_handler_registry",),
        emits=("delta_handler_registry.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.act.delta_handler_registry import InMemoryDeltaHandlerRegistry

    # 接缝只提供中性能力容器；默认 handler 由独立 provider 统一安装。
    ctx.provide("delta_handler_registry", InMemoryDeltaHandlerRegistry())


__all__ = ["setup"]
