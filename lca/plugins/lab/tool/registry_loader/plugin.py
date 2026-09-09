"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.registry_loader
stage: tool
kind: PROVIDER
description: Load the lab tool registry from YAML at boot.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.tool.registry_loader",
    stage="tool",
    kind="PROVIDER",
    description='Load the lab tool registry from YAML at boot.',
    node_id="plugin",
    source_module="lca.plugins.lab.registry_loader.plugin.plugin",
    source_class="plugin",
    provides=['tool_registry_loaded'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
