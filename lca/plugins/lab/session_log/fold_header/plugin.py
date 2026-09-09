"""fold_header.plugin — Session-log marker provider.

provider: yes
description: Fold the session log header into a step header.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.session_log.fold_header",
    "stage": "session_log",
    "kind": "PROVIDER",
    "description": "Fold the session log header into a step header.",
    "module": "lca.plugins.lab.session_log.fold_header.plugin",
    "provides": ["lab.session"],
    "requires": ["lab.session"],
    "inputs": [],
    "outputs": [{"port": "event", "kind": "event"}],
    "out_capabilities": ["lab.session_log_marker"],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
