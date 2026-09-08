# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Observers hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.observers import ObserverPlugin
_instance = ObserverPlugin()
_LAB_HOOKS["lab.hook.observers"] = _instance

__all__ = ["_instance"]
