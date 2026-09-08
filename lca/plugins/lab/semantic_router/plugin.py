# PR-A.3 — simplified plugin that doesn't depend on LCA plugin system
"""Semantic router hook plugin for agent_lab prototype."""

from lca.plugins.lab.internal.loader import _LAB_HOOKS

from agent_lab.plugins.semantic_router import SemanticRouterPlugin
_instance = SemanticRouterPlugin()
_LAB_HOOKS["lab.hook.semantic_router"] = _instance

__all__ = ["_instance"]
