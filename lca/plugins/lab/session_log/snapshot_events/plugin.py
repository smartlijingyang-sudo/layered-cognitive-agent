"""snapshot_events.plugin — Session-log marker provider.

provider: yes
description: Snapshot session log events for resume.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.snapshot_events",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Snapshot session log events for resume.",
    "module": "lca.plugins.lab.session_log.snapshot_events.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
