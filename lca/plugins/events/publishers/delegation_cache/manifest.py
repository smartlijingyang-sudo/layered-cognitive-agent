"""DelegationCachePlugin Manifest（ADR-0180）。

业务方 plugin 在 :mod:`lca.plugins.events.publishers` 统一目录下。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.event import Category
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.events.publishers.delegation_cache.plugin import (
    PUBLISHER_PLUGIN_ID,
    DelegationCachePlugin,
)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="delegation_cache",
    provides=["delegation.cache_observation"],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "DelegationCachePlugin（ADR-0180 试点）：publisher plugin；"
        "通过 EventMechanism.send 发 team.delegation.cache_hit。"
    ),
    test_suite="tests/plugins/events/publishers/test_delegation_cache.py",
    functional_group=FunctionalGroup.G8_COLLAB,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G8_COLLAB,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.TURN,)),
        authority=AuthorityContract(grants=("delegation.cache",)),
        observability=EvidenceContract(descriptors=("delegation.cache.hit",)),
    ),
    ownership=OwnershipDeclaration(
        reads=("team.awareness",),
        emits=(f"event.{Category.TEAM_DELEGATION_CACHE_HIT.value}",),
        state_mutation="forbidden",
    ),
)
async def setup_delegation_cache(ctx: PluginContext, config: _Config) -> None:
    """DelegationCachePlugin boot：构造单例 + provide 给 ctx。"""
    plugin_instance = DelegationCachePlugin()
    ctx.provide(PUBLISHER_PLUGIN_ID, plugin_instance)


__all__ = ["PUBLISHER_PLUGIN_ID"]
