"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_visible.manifest_commit
stage: model_visible
kind: PROVIDER
description: Commit the final manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.model_visible.manifest_commit",
    "stage": "model_visible",
    "kind": "PROVIDER",
    "description": "Commit the final manifest.",
    "module": "lca.plugins.lab.model_visible.manifest_commit.plugin",
    "provides": [],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
