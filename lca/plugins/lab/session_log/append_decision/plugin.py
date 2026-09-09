"""append_decision.plugin — Session-log marker provider.

provider: yes
description: Session.append(graph.decision.v1).
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.append_decision",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Session.append(graph.decision.v1).",
    "module": "lca.plugins.lab.session_log.append_decision.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
