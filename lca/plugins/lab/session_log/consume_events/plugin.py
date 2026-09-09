"""consume_events.plugin — Session-log marker provider.

provider: yes
description: Consume session log events from the journal.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.consume_events",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Consume session log events from the journal.",
    "module": "lca.plugins.lab.session_log.consume_events.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
