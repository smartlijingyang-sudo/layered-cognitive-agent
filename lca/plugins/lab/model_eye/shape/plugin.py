"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.shape
stage: model_eye
kind: PROVIDER
description: Shape the frozen manifest into the model-visible input bytes.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_eye.shape",
    "stage": "model_eye",
    "kind": "PROVIDER",
    "description": "Shape the frozen manifest into the model-visible input bytes.",
    "module": "lca.plugins.lab.model_eye.shape.plugin",
    "provides": ["model_visible_bytes"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
