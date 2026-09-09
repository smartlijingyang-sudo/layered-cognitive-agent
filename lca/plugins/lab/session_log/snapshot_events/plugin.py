"""snapshot_events.plugin — Session-log marker provider.

provider: yes
description: Snapshot session log events for resume.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.session_log.snapshot_events",
    stage="session_log",
    kind="PROVIDER",
    description='Snapshot session log events for resume.',
    node_id="plugin",
    source_module="lca.plugins.lab.snapshot_events.plugin.plugin",
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
