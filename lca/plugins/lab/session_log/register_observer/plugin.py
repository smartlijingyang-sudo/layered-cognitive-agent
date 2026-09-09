"""register_observer.plugin — Session-log marker provider.

provider: yes
description: Register an observer plugin for session log events.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.session_log.register_observer",
    stage="session_log",
    kind="PROVIDER",
    description='Register an observer plugin for session log events.',
    node_id="plugin",
    source_module="lca.plugins.lab.register_observer.plugin.plugin",
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
