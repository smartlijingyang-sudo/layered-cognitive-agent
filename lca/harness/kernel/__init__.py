"""Harness kernel — scoped plugin host + context propagation."""

from lca.harness.kernel.scope import ScopedPluginHost, current_scope

__all__ = ["ScopedPluginHost", "current_scope"]
