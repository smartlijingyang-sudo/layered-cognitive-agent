# PR-D final 2/2 — control.observe_checkpoint real @plugin carrier
"""Real carrier for ``agent_lab.plugins.observers.ObserverPlugin``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ObserverPlugin`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.control.observe_checkpoint``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/control/observe_checkpoint/plugin.py replaced by this carrier
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
    id="lab.control.observe_checkpoint",
    stage="control",
    kind="TRANSFORMER",
    description='Observe node_start / node_end events for checkpointing.',
    node_id='observe_checkpoint',
    source_module='agent_lab.plugins.observers',
    source_class='ObserverPlugin',
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

class _ObserveCheckpointNode(Worker):
    factory = "observe_checkpoint_node"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.control.ops import LcaControlCheckpointProvider
        provider = LcaControlCheckpointProvider.from_node_config(node.config)
        out_port = node.config.get("to", "checkpoint_event")
        event_type = node.config.get("event_type", "checkpoint")
        return provider.emit(event_type=event_type, event_log=inputs.get("in_event_log"), out_port=out_port)

register_worker("observe_checkpoint_node", _ObserveCheckpointNode)
register_worker("observe_checkpoint", _ObserveCheckpointNode)
register_worker("lab.observe_checkpoint_node", _ObserveCheckpointNode)
