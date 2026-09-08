# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Events hook plugin for agent_lab prototype.

This is a simplified version that just populates _LAB_HOOKS without
using the @plugin decorator, so it works in the prototype without
requiring the full LCA plugin system.
"""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

# Populate at import time
from agent_lab.plugins.events import EventSinkPlugin
_instance = EventSinkPlugin()
_LAB_HOOKS["lab.hook.events"] = _instance

__all__ = ["_instance"]
