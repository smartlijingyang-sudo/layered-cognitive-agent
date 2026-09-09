"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.passthrough.prefix
stage: passthrough
kind: PROVIDER
description: Prefix the input text.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.passthrough.prefix",
    "stage": "passthrough",
    "kind": "PROVIDER",
    "description": "Prefix the input text.",
    "module": "lca.plugins.lab.passthrough.prefix.plugin",
    "provides": [],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
