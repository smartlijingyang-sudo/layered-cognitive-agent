# PR-D final 2/2 — control.discard real @plugin carrier
"""Real carrier for ``agent_lab.plugins.control_slots.ControlSlotsPlugin``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ControlSlotsPlugin`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.control.discard``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/control/discard/plugin.py replaced by this carrier
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
    id="lab.control.discard",
    stage="control",
    kind="PRODUCER",
    description='Discard an output (sink only).',
    node_id='discard',
    source_module='agent_lab.plugins.control_slots',
    source_class='ControlSlotsPlugin',
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
from agent_lab.primitives.artifact import Artifact, ArtifactKind

class _Discard(Worker):
    factory = "discard"

    def execute(self, node, inputs, seams=None):
        from agent_lab.primitives.artifact import Artifact, ArtifactKind
        src = node.config.get("from", node.ins[0])
        out_port = node.config.get("to", node.outs[0])
        src_a = inputs.get(src)
        return {out_port: Artifact(kind=ArtifactKind.FACT, content={"discarded": True, "digest": src_a.short_id() if src_a else None}, schema_ref="discard.v1")}

register_worker("discard", _Discard)
register_worker("lab.discard", _Discard)
