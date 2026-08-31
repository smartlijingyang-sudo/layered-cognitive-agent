"""Search Service Definition plugin — Tier-1."""

from __future__ import annotations

from pydantic import BaseModel

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="lca-search-service",
    provides=["search"],
    implements=[],
    layer="L0",
    effects="tools",
    description="Provide the Search Definition service (ProviderDispatch + search fn table).",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    kind=PluginKind.SEAM,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-search-service.checked', 'lca-search-service.served'),
        revision="v1",
    ),
    relations=(),

    ownership=OwnershipDeclaration(
        reads=('search',),
        emits=('search.checked',),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.capability.search import SearchService

    ctx.provide("search", SearchService())
