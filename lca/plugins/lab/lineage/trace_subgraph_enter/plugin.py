"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.lineage.trace_subgraph_enter
stage: lineage
kind: PROVIDER
description: Trace subgraph-enter lineage event.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.lineage.trace_subgraph_enter",
    stage="lineage",
    kind="PROVIDER",
    description='Trace subgraph-enter lineage event.',
    node_id="plugin",
    source_module="lca.plugins.lab.trace_subgraph_enter.plugin.plugin",
    source_class="plugin",
    provides=[],
    requires=['lab.session'],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
