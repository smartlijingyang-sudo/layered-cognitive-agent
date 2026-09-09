"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.llm.call_llm
stage: llm
kind: PROVIDER
description: Call the LLM with assembled messages.
"""
from __future__ import annotations

from lca.plugins.lab.internal.loader import _LAB_HOOKS

_MARKER = {
    "id": "lab.llm.call_llm",
    "stage": "llm",
    "kind": "PROVIDER",
    "description": "Call the LLM with assembled messages.",
    "module": "lca.plugins.lab.llm.call_llm.plugin",
    "provides": ["llm_response"],
    "requires": ["llm_messages"],
    "inputs": [],
    "outputs": [{"port": "out", "kind": "artifact"}],
    "out_capabilities": [],
}

_LAB_HOOKS[_MARKER["id"]] = _MARKER

__all__ = []
