"""Auto-reflected marker provider — replaces PR-D final 2/2 carrier.

provider: yes
id: lab.llm.commit_manifest
stage: llm
kind: PROVIDER
description: Commit a frozen ContextManifest.
"""
from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier

_CARRIER = LabCarrier(
    id="lab.llm.commit_manifest",
    stage="llm",
    kind="PROVIDER",
    description='Commit a frozen ContextManifest.',
    node_id="plugin",
    source_module="lca.plugins.lab.commit_manifest.plugin.plugin",
    source_class="plugin",
    provides=['llm_manifest'],
    requires=[],
    inputs=(),
    outputs=(("out", "artifact"),),
    out_capabilities=(),
)


def setup(ctx, config):
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
