"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_visible.history_attach
stage: model_visible
kind: PROVIDER
description: Attach the per-session history to the prompt.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_visible.history_attach",
    "stage": "model_visible",
    "kind": "PROVIDER",
    "description": "Attach the per-session history to the prompt.",
    "module": "lca.plugins.lab.model_visible.history_attach.plugin",
    "provides": [],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
