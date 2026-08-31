"""EffectHandlerRegistry Seam Definition plugin — Tier-1."""

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
    id="lca-effect-handler-registry-seam",
    provides=["effect_handler_registry"],
    requires=[],
    implements=["EffectHandlerRegistry"],
    layer="L2",
    effects="none",
    description="Provide the EffectHandlerRegistry Definition service.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=("plugin.serve",),
        evidence=(
            "lca-effect-handler-registry-seam.checked",
            "lca-effect-handler-registry-seam.served",
        ),
        revision="v1",
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("effect_handler_registry",),
        emits=("effect_handler_registry.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.plugins.providers.act.effect_handlers import InMemoryEffectHandlerRegistry

    # A seam declares an empty capability container.  The separately enabled
    # provider plugin owns all default handler registration.
    ctx.provide("effect_handler_registry", InMemoryEffectHandlerRegistry())


__all__ = ["setup"]
