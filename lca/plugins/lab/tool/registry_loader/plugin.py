"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.registry_loader
stage: tool
kind: PROVIDER
description: Load the lab tool registry from YAML at boot.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.tool.registry_loader",
    "stage": "tool",
    "kind": "PROVIDER",
    "description": "Load the lab tool registry from YAML at boot.",
    "module": "lca.plugins.lab.tool.registry_loader.plugin",
    "provides": ["tool_registry_loaded"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
