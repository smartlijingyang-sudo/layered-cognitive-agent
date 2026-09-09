"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.event.tail
stage: event
kind: PROVIDER
description: Tail the event bus for a filter.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.event.tail",
    "stage": "event",
    "kind": "PROVIDER",
    "description": "Tail the event bus for a filter.",
    "module": "lca.plugins.lab.event.tail.plugin",
    "provides": ["event_tail"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
