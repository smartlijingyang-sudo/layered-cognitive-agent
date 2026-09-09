# PR-D final cleanup — self-contained hook plugin (no agent_lab dependency)
"""Parsers hook plugin for the lab prototype.

Replaces the deleted agent_lab.plugins.* class with a self-contained
GraphPlugin subclass from lca.plugins.lab.internal.hook_factories. The
hook behaviour is now a no-op marker (real work is delegated to the
LCA plugin system + the per-phase worker nodes).
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS
from lca.plugins.lab.internal.hook_factories import ParseDecisionPlugin

_instance = ParseDecisionPlugin()
_LAB_HOOKS["lab.hook.parsers"] = _instance

__all__ = ["_instance"]
