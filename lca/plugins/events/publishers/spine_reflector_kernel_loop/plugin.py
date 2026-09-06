# COMPAT(owner: ADR-0194 P2-14, from: spine_reflector_kernel_loop plugin emit,
# to: lca.loop.kernel_loop_emit,
# delete_when: rg "spine_reflector_kernel_loop" 生产引用归零(P2-16 bundle 已删),
# forbidden_new_usage: 新 emit 走 lca.loop.kernel_loop_emit)
"""spine_reflector_kernel_loop COMPAT shim (ADR-0194 P2-14)."""

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
from lca.loop.kernel_loop_emit import (
    emit_kernel_boot_completed,
    emit_kernel_boot_start,
    emit_loop_fork,
)

__all__ = [
    "ReflectorClass",
    "emit_kernel_boot_completed",
    "emit_kernel_boot_start",
    "emit_loop_fork",
    "setup",
]


class _Config(BaseModel):
    model_config = {"extra": "forbid"}


class ReflectorClass:
    """Publisher marker for yaml auth matrix (legacy)."""


@plugin(
    id="events.spine.reflector.kernel_loop",
    provides=["event.bus.reflector.kernel_loop"],
    requires=[],
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description="COMPAT: kernel_loop spine EPs migrated to lca.loop (ADR-0194 P2-14).",
    test_suite="tests/plugins/events/publishers/test_events_spine_reflector_kernel_loop.py",
    functional_group=FunctionalGroup.G0_CON_KERNEL,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G0_CON_KERNEL,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("event.bus.publish",)),
        observability=EvidenceContract(
            descriptors=("event.bus.reflector.kernel_loop.published",),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus",),
        emits=(
            "spine.kernel.boot.start",
            "spine.kernel.boot.completed",
            "spine.loop.fork",
        ),
        state_mutation="forbidden",
    ),
    marker_class=ReflectorClass,
)
async def setup(ctx: PluginContext, config: _Config) -> None:
    del config
    ctx.provide("event.bus.reflector.kernel_loop", ReflectorClass)
