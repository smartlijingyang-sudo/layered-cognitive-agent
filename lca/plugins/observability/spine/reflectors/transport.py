"""``spine.reflector.transport`` — carrier EXECUTION_POINTS plugin surface.

Emit helpers live in
:mod:`lca.infrastructure.observability.spine.transport_emit` so the
webserver carrier can call them without importing this plugin package
(plugin-package independence). This plugin re-exports those helpers and
publishes a marker capability for profile composition.
"""

from __future__ import annotations

from typing import Any

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
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.transport_emit import (
    emit_carrier_exception_caught,
    emit_carrier_exception_finally,
    emit_kernel_run_cancelled,
    emit_kernel_run_start,
    emit_kernel_run_stop,
    emit_transport_route_enter,
    emit_transport_route_exit,
    emit_transport_sse_publish,
)


@plugin(
    id="spine.reflector.transport",
    provides=("transport_reflector",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "Transport / kernel.run reflector surface — re-exports carrier "
        "emit helpers; active spine is installed by spine.core."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_reflector_transport",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_span_context",)),
        observability=EvidenceContract(descriptors=("spine.reflector.transport",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("transport_reflector",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Publish a marker capability; emit helpers are infrastructure-owned."""
    del config
    ctx.provide("transport_reflector", True)


__all__ = [
    "emit_carrier_exception_caught",
    "emit_carrier_exception_finally",
    "emit_kernel_run_cancelled",
    "emit_kernel_run_start",
    "emit_kernel_run_stop",
    "emit_transport_route_enter",
    "emit_transport_route_exit",
    "emit_transport_sse_publish",
    "setup",
]
