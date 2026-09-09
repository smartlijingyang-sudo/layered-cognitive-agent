"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.llm.assemble_messages
stage: llm
kind: PROVIDER
description: Assemble OpenAI-style messages from a ContextManifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.llm.assemble_messages",
    stage="llm",
    kind="PROVIDER",
    description='Assemble OpenAI-style messages from a ContextManifest.',
    node_id="plugin",
    source_module="lca.plugins.lab.assemble_messages.plugin.plugin",
    source_class="plugin",
    provides=['llm_messages'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
