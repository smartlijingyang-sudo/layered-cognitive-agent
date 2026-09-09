"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.event.emit
stage: event
kind: PROVIDER
description: Emit a domain event into the event bus.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.event.emit",
    "stage": "event",
    "kind": "PROVIDER",
    "description": "Emit a domain event into the event bus.",
    "module": "lca.plugins.lab.event.emit.plugin",
    "provides": ["event_emit"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
