"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.tool.expose_schemas
stage: tool
kind: PROVIDER
description: Expose tool schemas to the model-visible manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.tool.expose_schemas",
    stage="tool",
    kind="PROVIDER",
    description='Expose tool schemas to the model-visible manifest.',
    node_id="plugin",
    source_module="lca.plugins.lab.expose_schemas.plugin.plugin",
    source_class="plugin",
    provides=['tool_schemas_exposed'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
