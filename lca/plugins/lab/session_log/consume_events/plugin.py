"""consume_events.plugin — Session-log marker provider.

provider: yes
description: Consume session log events from the journal.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.session_log.consume_events",
    stage="session_log",
    kind="PROVIDER",
    description='Consume session log events from the journal.',
    node_id="plugin",
    source_module="lca.plugins.lab.consume_events.plugin.plugin",
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
