"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_visible.messages_merge
stage: model_visible
kind: PROVIDER
description: Merge multiple message sources into one prompt.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.model_visible.messages_merge",
    stage="model_visible",
    kind="PROVIDER",
    description='Merge multiple message sources into one prompt.',
    node_id="plugin",
    source_module="lca.plugins.lab.messages_merge.plugin.plugin",
    source_class="plugin",
    provides=[],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
