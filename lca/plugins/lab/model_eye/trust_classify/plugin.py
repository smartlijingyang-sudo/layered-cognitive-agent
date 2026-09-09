"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.model_eye.trust_classify
stage: model_eye
kind: PROVIDER
description: Tag tool results with a trust classification.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.model_eye.trust_classify",
    stage="model_eye",
    kind="PROVIDER",
    description='Tag tool results with a trust classification.',
    node_id="plugin",
    source_module="lca.plugins.lab.trust_classify.plugin.plugin",
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
