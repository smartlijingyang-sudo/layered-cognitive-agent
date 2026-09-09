"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.expose_schemas
stage: tool
kind: PROVIDER
description: Expose tool schemas to the model-visible manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.tool.expose_schemas",
    "stage": "tool",
    "kind": "PROVIDER",
    "description": "Expose tool schemas to the model-visible manifest.",
    "module": "lca.plugins.lab.tool.expose_schemas.plugin",
    "provides": ["tool_schemas_exposed"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
