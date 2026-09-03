"""``spine.wrap.ctx_intercept`` — publish the ctx_intercept installer.

Installer implementation:
:func:`~lca.plugins.observability.spine.runtime_hooks.install_ctx_intercept_hook`.
This module only hosts the ``@plugin`` Manifest so Profile resolution can
load ``lca.plugins.observability.spine.wraps.ctx_intercept``.
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.plugins.observability.spine.runtime_hooks import install_ctx_intercept_hook


@plugin(
    id="spine.wrap.ctx_intercept",
    provides=("ctx_intercept_wrap",),
    # Pipeline is resolved at emit-time via set_active_pipeline_accessor.
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "ctx_intercept wrap kind — replaces a named host attribute with a "
        "start/end bracketing wrapper routed through emit_pipeline; the "
        "un-patch is registered via ctx.effect so the kernel owns teardown."
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
        observability=EvidenceContract(descriptors=("spine.wrap.ctx_intercept",)),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=(),
        emits=("ctx_intercept_wrap",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Publish the ``ctx_intercept`` installer under ``ctx_intercept_wrap``."""
    del config  # config-free; targets are chosen by the caller.
    ctx.provide("ctx_intercept_wrap", install_ctx_intercept_hook)


__all__ = ["setup"]
