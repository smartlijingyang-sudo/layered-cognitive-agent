# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Control slots hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.control_slots import ControlSlotsPlugin
_instance = ControlSlotsPlugin()
_LAB_HOOKS["lab.hook.control_slots"] = _instance

__all__ = ["_instance"]
