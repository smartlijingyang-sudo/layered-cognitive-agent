# PR-D final 2/2 — control.perceive_context_node real @plugin carrier
"""Real carrier for ``agent_lab.nodes.control.perceive_context_node.plugin.PerceiveContextNode``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``PerceiveContextNode`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.control.perceive_context_node``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/control/perceive_context_node/plugin.py replaced by this carrier
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
    id="lab.control.perceive_context_node",
    stage="control",
    kind="PRODUCER",
    description='Control-plane wrapper around the perceive context producer.',
    node_id='perceive_context_node',
    source_module='agent_lab.nodes.control.perceive_context_node.plugin',
    source_class='PerceiveContextNode',
    provides=['perceive_context'],
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

class _PerceiveContextNode(Worker):
    factory = "perceive_context_node"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.control.ops_act import LcaControlPerceiveContextProvider
        from agent_lab.primitives.artifact import Artifact
        provider = LcaControlPerceiveContextProvider.from_node_config(node.config)
        out_port = node.config.get("to", "allowed")
        result = provider.evaluate(inputs.get("in_args"))
        return {out_port: result.get(out_port, Artifact(kind="fact", content={"allowed": True}))}

register_worker("perceive_context_node", _PerceiveContextNode)
register_worker("lab.perceive_context_node", _PerceiveContextNode)
