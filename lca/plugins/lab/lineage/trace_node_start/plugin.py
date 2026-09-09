"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.lineage.trace_node_start
stage: lineage
kind: PROVIDER
description: Trace node-start lineage event.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.lineage.trace_node_start",
    "stage": "lineage",
    "kind": "PROVIDER",
    "description": "Trace node-start lineage event.",
    "module": "lca.plugins.lab.lineage.trace_node_start.plugin",
    "provides": [],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
