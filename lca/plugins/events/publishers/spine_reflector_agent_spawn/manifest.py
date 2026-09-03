"""spine_reflector_agent_spawn Manifest（PR-5 单入口宇宙）。

publisher plugin 的 Manifest；与 ``plugin.py`` 中的 ``ReflectorClass``
marker 类配对，yaml ``publishers:`` 字段可按 id 引用。
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
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
from lca.plugins.events.publishers.spine_reflector_agent_spawn.plugin import (
    ReflectorClass,
)


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine_reflector_agent_spawn",
    provides=[],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "spine_reflector_agent_spawn publisher plugin（ADR-0181 PR-4）："
        "agent_loop + agent 5 个 emit 走 EventBus.publish。"
    ),
    test_suite="tests/plugins/events/publishers/test_spine_reflector_agent_spawn.py",
    functional_group=FunctionalGroup.G12_EVIDENCE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.publish",)),
        observability=EvidenceContract(descriptors=("event.spine_reflector_agent_spawn",)),
    ),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("event.spine.agent_loop.*", "event.spine.agent.*"),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_reflector_agent_spawn boot：marker class 已在 catalog，无需实例化。"""
    return None


__all__ = ["setup"]