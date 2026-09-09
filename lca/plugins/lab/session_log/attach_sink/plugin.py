"""attach_sink.plugin — Session-log marker provider.

provider: yes
description: Attach a sink to the session log stream.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.attach_sink",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Attach a sink to the session log stream.",
    "module": "lca.plugins.lab.session_log.attach_sink.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
