"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.trust_classify
stage: model_eye
kind: PROVIDER
description: Tag tool results with a trust classification.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_eye.trust_classify",
    "stage": "model_eye",
    "kind": "PROVIDER",
    "description": "Tag tool results with a trust classification.",
    "module": "lca.plugins.lab.model_eye.trust_classify.plugin",
    "provides": [],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
