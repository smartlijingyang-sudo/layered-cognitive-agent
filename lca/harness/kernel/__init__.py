"""Harness kernel — scoped plugin host + context propagation."""

from lca.harness.kernel.compat import manifest_from_entry, manifest_from_spec
from lca.harness.kernel.scope import ScopedPluginHost, current_scope

__all__ = [
    "ScopedPluginHost",
    "current_scope",
    "manifest_from_entry",
    "manifest_from_spec",
]
