"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.see
stage: model_eye
kind: PROVIDER
description: Project the model-visible input bundle into a Manifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.model_eye.see",
    stage="model_eye",
    kind="PROVIDER",
    description='Project the model-visible input bundle into a Manifest.',
    node_id="plugin",
    source_module="lca.plugins.lab.see.plugin.plugin",
    source_class="plugin",
    provides=['model_visible_manifest'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
