"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_visible.prompt_assemble
stage: model_visible
kind: PROVIDER
description: Assemble the final prompt from the visible manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_visible.prompt_assemble",
    "stage": "model_visible",
    "kind": "PROVIDER",
    "description": "Assemble the final prompt from the visible manifest.",
    "module": "lca.plugins.lab.model_visible.prompt_assemble.plugin",
    "provides": ["model_visible_prompt"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
