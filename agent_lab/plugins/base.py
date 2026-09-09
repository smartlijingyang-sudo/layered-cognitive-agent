"""Plugin base — hook helper re-exports only (compat shim).

PR-D final cleanup — the GraphPlugin base class and register_plugin
decorator are no longer needed:

- The 8 GraphPlugin subclasses (EventSinkPlugin, ObserverPlugin,
  ParseDecisionPlugin, SemanticRouterPlugin, ControlSlotsPlugin,
  ObservationRenderPlugin, MemoryExtractPlugin, ToolDispatchGuardPlugin)
  were deleted from agent_lab.plugins. The new hook carriers in
  lca.plugins.lab.<hook>/plugin.py use lca.plugins.lab.internal.hooks
  GraphPlugin (the data class) via lca.plugins.lab.internal.hook_factories.
- The agent_lab_default GraphPlugin class is therefore dead code.
- The agent_lab register_plugin no-op decorator is also dead code
  (no plugin uses it any more).

What stays:
- Hook helper re-exports (Bind, HookContext, HookEvent, fanout_hooks)
  for any code that still imports them from this path.

delete-when (PR-D final acceptance):
- agent_lab_default is dead — no caller in lca/, tests/, scripts/
- This module is only kept for the hook helper re-exports; once all
  consumers import those from lca.plugins.lab.internal.hooks, this
  whole module can be deleted.
"""

from lca.plugins.lab.internal.hooks import (
    Bind,
    GraphPlugin,
    HookContext,
    HookEvent,
    fanout_hooks,
)

__all__ = [
    "Bind",
    "GraphPlugin",
    "HookContext",
    "HookEvent",
    "fanout_hooks",
]