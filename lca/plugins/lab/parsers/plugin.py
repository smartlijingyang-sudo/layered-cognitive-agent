# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Parsers hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.parsers import ParseDecisionPlugin
_instance = ParseDecisionPlugin()
_LAB_HOOKS["lab.hook.parsers"] = _instance

__all__ = ["_instance"]
