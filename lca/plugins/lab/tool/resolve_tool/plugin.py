"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.resolve_tool
stage: tool
kind: PROVIDER
description: Resolve a tool name to a Tool instance.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.tool.resolve_tool",
    "stage": "tool",
    "kind": "PROVIDER",
    "description": "Resolve a tool name to a Tool instance.",
    "module": "lca.plugins.lab.tool.resolve_tool.plugin",
    "provides": ["tool_resolved"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
