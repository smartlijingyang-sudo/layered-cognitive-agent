"""spine_reflector_perception Manifest（PR-5 单入口宇宙）。

publisher / sink / subscriber plugin 的 Manifest；与 ``plugin.py``（或
``sink.py`` / ``subscriber.py``）中的 marker 类配对，yaml ``publishers:``
/ ``subscribers:`` 字段可按 id 引用。
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
from lca.plugins.events.publishers.spine_reflector_perception.plugin import ReflectorClass


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine_reflector_perception",
    provides=[],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        'Perception reflectors：spine.perception.* 系列 emit（ADR-0183 PR-6）。'
    ),
    test_suite="tests/plugins/events/publishers/test_spine_reflector_perception.py",
    functional_group=FunctionalGroup.G4_PERCEPTION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G4_PERCEPTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.publisher",)),
        observability=EvidenceContract(descriptors=("event.spine_reflector_perception",)),
    ),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("event.spine_reflector_perception",),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_reflector_perception boot：marker class 已在 catalog，无需实例化。"""
    return None


__all__ = ["setup_"]
