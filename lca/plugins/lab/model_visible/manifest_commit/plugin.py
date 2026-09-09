"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_visible.manifest_commit
stage: model_visible
kind: PROVIDER
description: Commit the final manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.model_visible.manifest_commit",
    stage="model_visible",
    kind="PROVIDER",
    description='Commit the final manifest.',
    node_id="plugin",
    source_module="lca.plugins.lab.manifest_commit.plugin.plugin",
    source_class="plugin",
    provides=[],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
