# PR-D final 2/2 — perceive.memory real @plugin carrier
"""Real carrier for ``agent_lab.nodes.perceive.memory.plugin.PerceiveMemory``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``PerceiveMemory`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.perceive.memory``
Output capability: ``lab.perceive.memory.out:memory_items``

delete-when (PR-D final 2/2):
- agent_lab/nodes/perceive/memory/plugin.py replaced by this carrier
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
    id="lab.perceive.memory",
    stage="perceive",
    kind="TRANSFORMER",
    description='Pull relevant memory items from the remember store.',
    node_id='memory',
    source_module='agent_lab.nodes.perceive.memory.plugin',
    source_class='PerceiveMemory',
    provides=['memory_items'],
    requires=[],
    emits=['memory_items'],
    inputs=[('query', 'FACT', False), ('state', 'FACT', False)],
    outputs=[('memory_items', 'FACT')],
    out_capabilities=['lab.perceive.memory.out:memory_items'],
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
from lca.plugins.lab.perceive.ops import fold_memory_items
from agent_lab.primitives.artifact import Artifact, ArtifactKind, make_text, make_message, make_exception

class _PerceiveMemory(Worker):
    factory = "perceive.memory"

    def execute(self, node, inputs, seams=None):
        del node
        return fold_memory_items(
            memory_artifact=inputs.get("memory_ref"),
            state_artifact=inputs.get("state")
        )

register_worker("perceive.memory", _PerceiveMemory)
register_worker("lab.perceive.memory", _PerceiveMemory)
