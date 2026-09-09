"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.see
stage: model_eye
kind: PROVIDER
description: Project the model-visible input bundle into a Manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_eye.see",
    "stage": "model_eye",
    "kind": "PROVIDER",
    "description": "Project the model-visible input bundle into a Manifest.",
    "module": "lca.plugins.lab.model_eye.see.plugin",
    "provides": ["model_visible_manifest"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
