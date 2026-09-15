"""think.history_assemble — typed-boundary adapter for RunSessionWriter.

The graph node registered as ``think::history.derive`` wraps the pure
``history_assemble`` async fn in :mod:`lca.framework.graph.nodes.history_assemble`
with a ``NodeExecutor`` adapter so :class:`lca.harness.plugin_api.PluginContext`
can expose it under the composite key.

delete-when: never — this plugin is the typed-boundary adapter required by
``bundles/concept/history_assemble.yaml``'s ``factory: history.derive``.
"""

from lca.plugins.think.history_assemble.execute import (
    HistoryAssembleExecutor,
    setup,
)

__all__ = ["HistoryAssembleExecutor", "setup"]
