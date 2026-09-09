"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.guard
stage: model_eye
kind: PROVIDER
description: Apply PII / secrets redaction on the visible manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_eye.guard",
    "stage": "model_eye",
    "kind": "PROVIDER",
    "description": "Apply PII / secrets redaction on the visible manifest.",
    "module": "lca.plugins.lab.model_eye.guard.plugin",
    "provides": ["model_visible_redacted"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
