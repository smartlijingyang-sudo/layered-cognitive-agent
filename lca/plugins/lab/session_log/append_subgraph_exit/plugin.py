"""append_subgraph_exit.plugin — Session-log marker provider.

provider: yes
description: Session.append(graph.subgraph_exit.v1).
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.session_log.append_subgraph_exit",
    stage="session_log",
    kind="PROVIDER",
    description='Session.append(graph.subgraph_exit.v1).',
    node_id="plugin",
    source_module="lca.plugins.lab.append_subgraph_exit.plugin.plugin",
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
