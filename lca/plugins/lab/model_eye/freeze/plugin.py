"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.freeze
stage: model_eye
kind: PROVIDER
description: Freeze the manifest into an immutable ContextManifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_eye.freeze",
    "stage": "model_eye",
    "kind": "PROVIDER",
    "description": "Freeze the manifest into an immutable ContextManifest.",
    "module": "lca.plugins.lab.model_eye.freeze.plugin",
    "provides": ["model_visible_frozen"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
