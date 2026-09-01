"""``spine.wrap.ctx_effect`` — publish the ctx_effect installer.

Installer implementation:
:func:`~lca.plugins.observability.spine.runtime_hooks.install_ctx_effect_hook`.
This module only hosts the ``@plugin`` Manifest so Profile resolution can
load ``lca.plugins.observability.spine.wraps.ctx_effect``.
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
from lca.plugins.observability.spine.runtime_hooks import install_ctx_effect_hook


@plugin(
    id="spine.wrap.ctx_effect",
    provides=("ctx_effect_wrap",),
    # Pipeline is resolved at emit-time via set_active_pipeline_accessor
    # (installed by spine.emit_pipeline); setup only publishes the installer.
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects=EffectClass.NONE,
    description=(
        "ctx_effect wrap kind — emits a context-lifecycle start event on "
        "install and an end event from a ctx.effect disposer, both routed "
        "through emit_pipeline so every enabled FieldProducer contributes."
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
        observability=EvidenceContract(descriptors=("spine.wrap.ctx_effect",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("ctx_effect_wrap",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Publish the ``ctx_effect`` installer under ``ctx_effect_wrap``.

    The plugin provides the *installer*, not an installed hook: which
    execution points get a lifecycle bracket is a profile decision made
    by ``spine.core`` at boot, so this setup stays free of I/O and of any
    hard-coded execution point.
    """
    del config  # config-free; execution points are chosen by the caller.
    ctx.provide("ctx_effect_wrap", install_ctx_effect_hook)


__all__ = ["setup"]
