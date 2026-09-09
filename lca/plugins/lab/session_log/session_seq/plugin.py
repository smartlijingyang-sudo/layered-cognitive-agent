"""session_seq.plugin — Session-log marker provider.

provider: yes
description: Allocate a per-session sequence number.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.session_seq",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Allocate a per-session sequence number.",
    "module": "lca.plugins.lab.session_log.session_seq.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
