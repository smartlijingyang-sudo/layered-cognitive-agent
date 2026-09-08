# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Memory extract hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.memory_extract import MemoryExtractPlugin
_instance = MemoryExtractPlugin()
_LAB_HOOKS["lab.hook.memory_extract"] = _instance

__all__ = ["_instance"]
