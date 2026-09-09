"""fanout_observers.plugin — Session-log marker provider.

provider: yes
description: Fan session log events to observer plugins.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.fanout_observers",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Fan session log events to observer plugins.",
    "module": "lca.plugins.lab.session_log.fanout_observers.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
