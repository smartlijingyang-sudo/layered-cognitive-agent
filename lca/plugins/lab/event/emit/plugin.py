"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.event.emit
stage: event
kind: PROVIDER
description: Emit a domain event into the event bus.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.event.emit",
    stage="event",
    kind="PROVIDER",
    description='Emit a domain event into the event bus.',
    node_id="plugin",
    source_module="lca.plugins.lab.emit.plugin.plugin",
    source_class="plugin",
    provides=['event_emit'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
