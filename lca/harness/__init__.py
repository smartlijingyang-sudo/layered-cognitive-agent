"""Harness kernel — re-exports plugin kernel + adds ScopedPluginHost.

The harness kernel is a thin wrapper around the existing plugin kernel
(``lca/layer0_infra/plugin/kernel/``), adding scope hierarchy and
async context propagation.

During Phase A, the existing plugin kernel remains the implementation;
the harness package provides the new architectural entry points.
"""

from lca.harness.kernel.scope import ScopedPluginHost, current_scope

# Re-export core types for convenience — code should import from
# ``lca.harness.kernel`` rather than reaching into ``layer0_infra.plugin.kernel``.
from lca.layer0_infra.plugin.kernel import (
    PluginContext,
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
    ServiceRecord,
    reconcile,
)

__all__ = [
    "PluginContext",
    "PluginHandle",
    "PluginHost",
    "PluginSpec",
    "PluginState",
    "ScopedPluginHost",
    "ServiceRecord",
    "current_scope",
    "reconcile",
]
