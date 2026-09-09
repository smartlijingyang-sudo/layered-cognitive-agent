"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.grant_check
stage: tool
kind: PROVIDER
description: Verify the tool call is within the grant.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.tool.grant_check",
    stage="tool",
    kind="PROVIDER",
    description='Verify the tool call is within the grant.',
    node_id="plugin",
    source_module="lca.plugins.lab.grant_check.plugin.plugin",
    source_class="plugin",
    provides=['tool_grant_checked'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
