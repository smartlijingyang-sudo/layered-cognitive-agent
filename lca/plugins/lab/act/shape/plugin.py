# PR-B — act.shape node plugin (minimal stub for loader registration)
"""act.shape — Decision → Intent for Body.act.

Stub plugin that registers a marker for the act.shape node in the
loader. The actual implementation lives in agent_lab/nodes/act/shape/
plugin.py and is reached via the node factory (not the plugin system).
PR-D will rewrite this as a full @plugin carrier.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_marker = {"id": "act.shape", "stage": "act"}
_LAB_HOOKS["lab.act.shape"] = _marker

__all__ = ["_marker"]