"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.event.tail
stage: event
kind: PROVIDER
description: Tail the event bus for a filter.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.event.tail",
    stage="event",
    kind="PROVIDER",
    description='Tail the event bus for a filter.',
    node_id="plugin",
    source_module="lca.plugins.lab.tail.plugin.plugin",
    source_class="plugin",
    provides=['event_tail'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
