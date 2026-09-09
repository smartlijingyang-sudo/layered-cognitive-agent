# PR-D final 2/2 — passthrough.identity real @plugin carrier
"""Real carrier for ``agent_lab.nodes.passthrough.identity.plugin.Identity``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``Identity`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.passthrough.identity``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/passthrough/identity/plugin.py replaced by this carrier
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
    id="lab.passthrough.identity",
    stage="passthrough",
    kind="PASSTHROUGH",
    description='Pass-through identity node.',
    node_id='identity',
    source_module='agent_lab.nodes.passthrough.identity.plugin',
    source_class='Identity',
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


class _Identity(Worker):
    factory = "identity"

    def execute(self, node, inputs, seams=None):
        src = node.config.get("from", node.ins[0])
        dst = node.config.get("to", node.outs[0])
        if src not in inputs:
            return {dst: Artifact(kind=ArtifactKind.TEXT, content="")}
        return {dst: inputs[src]}


for _f in ("identity", "passthrough.identity", "lab.passthrough.identity"):
    register_worker(_f, _Identity)
