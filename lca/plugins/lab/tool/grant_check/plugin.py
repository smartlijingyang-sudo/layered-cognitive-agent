"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.grant_check
stage: tool
kind: PROVIDER
description: Verify the tool call is within the grant.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.tool.grant_check",
    "stage": "tool",
    "kind": "PROVIDER",
    "description": "Verify the tool call is within the grant.",
    "module": "lca.plugins.lab.tool.grant_check.plugin",
    "provides": ["tool_grant_checked"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
