"""``spine.wrap.assembler`` — publish phase-graph ``wrap_instrument``.

The callable itself lives in
:mod:`lca.harness.declarative.compile.instrument_wrap` (harness must not
import plugins). This plugin re-exports it under ``assembler_wrap`` so
Profile / Bundle can select the assembler weave path the same way as the
other wrap kinds.
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
from lca.harness.declarative.compile.instrument_wrap import wrap_instrument
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin


@plugin(
    id="spine.wrap.assembler",
    provides=("assembler_wrap",),
    # Pipeline is resolved at emit-time via set_active_pipeline_accessor.
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "assembler wrap kind — publishes wrap_instrument so every phase "
        "graph node is bracketed with start/end events routed through "
        "emit_pipeline; wrappers stamp wrap_provenance='assembler'."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_wraps",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G12_EVIDENCE,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.read_span_context",)),
        observability=EvidenceContract(descriptors=("spine.wrap.assembler",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("assembler_wrap",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Publish ``wrap_instrument`` under ``assembler_wrap``."""
    del config  # config-free; node ids are chosen by the assembler.
    ctx.provide("assembler_wrap", wrap_instrument)


__all__ = ["setup"]
