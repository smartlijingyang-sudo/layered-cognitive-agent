"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.resolve_tool
stage: tool
kind: PROVIDER
description: Resolve a tool name to a Tool instance.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.tool.resolve_tool",
    stage="tool",
    kind="PROVIDER",
    description='Resolve a tool name to a Tool instance.',
    node_id="plugin",
    source_module="lca.plugins.lab.resolve_tool.plugin.plugin",
    source_class="plugin",
    provides=['tool_resolved'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
