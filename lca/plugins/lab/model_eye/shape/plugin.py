"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.shape
stage: model_eye
kind: PROVIDER
description: Shape the frozen manifest into the model-visible input bytes.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.model_eye.shape",
    stage="model_eye",
    kind="PROVIDER",
    description='Shape the frozen manifest into the model-visible input bytes.',
    node_id="plugin",
    source_module="lca.plugins.lab.shape.plugin.plugin",
    source_class="plugin",
    provides=['model_visible_bytes'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
