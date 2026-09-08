# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Tool guard hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.tool_guard import ToolDispatchGuardPlugin
_instance = ToolDispatchGuardPlugin()
_LAB_HOOKS["lab.hook.tool_guard"] = _instance

__all__ = ["_instance"]
