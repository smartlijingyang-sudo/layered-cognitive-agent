# PR-D final 2/2 — passthrough.rank_v2 real @plugin carrier
"""Real carrier for ``agent_lab.nodes.passthrough.rank_v2.plugin.RankV2``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``RankV2`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.passthrough.rank_v2``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/passthrough/rank_v2/plugin.py replaced by this carrier
  (test env: delete-when happens when LCA runtime with cordis
  is in place and the legacy plugin can be removed)
"""

from __future__ import annotations

from lca.plugins.lab.internal.hooks import (
    LabCarrier,
    bind_carrier,
)


# Carrier data: what the loader's register_carrier() needs.
_CARRIER = LabCarrier(
    id="lab.passthrough.rank_v2",
    stage="passthrough",
    kind="PASSTHROUGH",
    description='Rank v2.',
    node_id='rank_v2',
    source_module='agent_lab.nodes.passthrough.rank_v2.plugin',
    source_class='RankV2',
    provides=[],
    requires=[],
    emits=[],
    inputs=[],
    outputs=[],
    out_capabilities=[],
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


# Auto-bind on import so the loader walks these like any other plugin
# carrier — the setup() function is still callable from a real Cordis
# boot path for two-phase register.
bind_carrier(_CARRIER)


__all__ = ["setup", "_CARRIER"]


# --- PR-D worker execute -----------------------------------------------
from lca.plugins.lab.internal.worker import Worker, register_worker
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text


class _RankV2(Worker):
    factory = "passthrough__rank"

    def execute(self, node, inputs, seams=None):
        text_a = inputs.get("text")
        text = text_a.content if text_a else ""
        sep = node.config.get("split_on", "\n")
        keep = int(node.config.get("keep", 50))
        lines = text.split(sep) if text else []
        joined = sep.join(lines[:keep])
        if text_a is None:
            return {"out": Artifact(kind=ArtifactKind.TEXT, content="")}
        return {"out": Artifact(kind=text_a.kind, content=joined, schema_ref=text_a.schema_ref)}


register_worker("passthrough__rank", _RankV2)
register_worker("lab.passthrough.rank_v2", _RankV2)
