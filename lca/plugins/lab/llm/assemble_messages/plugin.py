"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.llm.assemble_messages
stage: llm
kind: PROVIDER
description: Assemble OpenAI-style messages from a ContextManifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.llm.assemble_messages",
    "stage": "llm",
    "kind": "PROVIDER",
    "description": "Assemble OpenAI-style messages from a ContextManifest.",
    "module": "lca.plugins.lab.llm.assemble_messages.plugin",
    "provides": ["llm_messages"],
    "requires": [],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
