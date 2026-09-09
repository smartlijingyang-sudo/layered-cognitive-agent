"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.llm.call_llm
stage: llm
kind: PROVIDER
description: Call the LLM with assembled messages.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.llm.call_llm",
    stage="llm",
    kind="PROVIDER",
    description='Call the LLM with assembled messages.',
    node_id="plugin",
    source_module="lca.plugins.lab.call_llm.plugin.plugin",
    source_class="plugin",
    provides=['llm_response'],
    requires=['llm_messages'],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
