"""Search Provider plugin — Tier-2."""

from __future__ import annotations

from pydantic import BaseModel, Field

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.protocols.composition.logic_address import LogicAddress


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["tavily"])


@plugin(
    id="lca-search-provider",
    requires=["search"],
    layer="L0",
    effects="tools",
    description="Register Search provider functions on the SearchService Definition.",
    test_suite="tests/test_plugin_alignment.py",
    kind=PluginKind.PROVIDER,


    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G10_COMPOSITION,
        control_slot=ControlSlot.OBSERVE_WILDCARD,
        scope=Scope.RUN,
        authority=('plugin.serve',),
        evidence=('lca-search-provider.checked', 'lca-search-provider.served'),
        revision="v1",
    ),
    relations=(),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    from lca.infrastructure.search.providers.tavily import search_tavily

    if "tavily" in config.providers:
        ctx.require("search").register("tavily", search_tavily)
