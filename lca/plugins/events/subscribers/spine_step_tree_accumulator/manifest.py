"""spine_step_tree_accumulator Manifest（PR-5 单入口宇宙）。

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
from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import SpineStepTreeAccumulator


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


@plugin(
    id="events.spine_step_tree_accumulator",
    provides=[],
    requires=[],
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        'SpineStepTreeAccumulator：构建 step tree（ADR-0181 PR-9）。'
    ),
    test_suite="tests/plugins/events/subscribers/test_spine_step_tree_accumulator.py",
    functional_group=FunctionalGroup.G12_EVIDENCE,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.subscriber",)),
        observability=EvidenceContract(descriptors=("event.spine_step_tree_accumulator",)),
    ),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("event.spine_step_tree_accumulator",),
        state_mutation="forbidden",
    ),
    marker_class=SpineStepTreeAccumulator,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    """spine_step_tree_accumulator boot：marker class 已在 catalog，无需实例化。"""
    return None


__all__ = ["setup_"]
