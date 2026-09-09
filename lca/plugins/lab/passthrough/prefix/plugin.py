"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.passthrough.prefix
stage: passthrough
kind: PROVIDER
description: Prefix the input text.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.passthrough.prefix",
    stage="passthrough",
    kind="PROVIDER",
    description='Prefix the input text.',
    node_id="plugin",
    source_module="lca.plugins.lab.prefix.plugin.plugin",
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
