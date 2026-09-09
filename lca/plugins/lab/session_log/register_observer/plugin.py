"""register_observer.plugin — Session-log marker provider.

provider: yes
description: Register an observer plugin for session log events.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.register_observer",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Register an observer plugin for session log events.",
    "module": "lca.plugins.lab.session_log.register_observer.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
