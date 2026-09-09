"""flush_sink.plugin — Session-log marker provider.

provider: yes
description: Flush a sink to its durable store.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.session_log.flush_sink",
    stage="session_log",
    kind="PROVIDER",
    description='Flush a sink to its durable store.',
    node_id="plugin",
    source_module="lca.plugins.lab.flush_sink.plugin.plugin",
    source_class="SessionLogEmitterPlugin",
    provides=["lab.session"],
    requires=["lab.session"],
    inputs=(),
    outputs=(("event", "event"),),
    out_capabilities=["lab.session_log_marker"],
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
