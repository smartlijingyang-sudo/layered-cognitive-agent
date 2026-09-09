"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.llm.commit_manifest
stage: llm
kind: PROVIDER
description: Commit a frozen ContextManifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.llm.commit_manifest",
    "stage": "llm",
    "kind": "PROVIDER",
    "description": "Commit a frozen ContextManifest.",
    "module": "lca.plugins.lab.llm.commit_manifest.plugin",
    "provides": ["llm_manifest"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
