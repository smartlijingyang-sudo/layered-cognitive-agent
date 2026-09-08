# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Observation hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.observation import ObservationRenderPlugin
_instance = ObservationRenderPlugin()
_LAB_HOOKS["lab.hook.observation"] = _instance

__all__ = ["_instance"]
