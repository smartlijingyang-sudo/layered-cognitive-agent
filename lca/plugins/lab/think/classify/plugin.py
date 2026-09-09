# PR-D final 2/2 — think.classify real @plugin carrier
"""Real carrier for ``agent_lab.nodes.think.classify.plugin.ThinkClassify``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ThinkClassify`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.think.classify``
Output capability: ``lab.think.classify.out:decision``

delete-when (PR-D final 2/2):
- agent_lab/nodes/think/classify/plugin.py replaced by this carrier
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
    id="lab.think.classify",
    stage="think",
    kind="TRANSFORMER",
    description='Classify LLMResponse into a Decision (lab action_type).',
    node_id='classify',
    source_module='agent_lab.nodes.think.classify.plugin',
    source_class='ThinkClassify',
    provides=['think_decision'],
    requires=[],
    emits=['think_decision'],
    inputs=[('response', 'MESSAGE', False)],
    outputs=[('decision', 'FACT')],
    out_capabilities=['lab.think.classify.out:decision'],
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

class _Think_Classify(Worker):
    factory = "think.classify"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.think.classify.ops import classify_response
        src = node.config.get("from", "response")
        out = node.config.get("to", "decision")
        fixture = (node.config.get("provider_config") or {}).get("fixture_classifier")
        decision = classify_response(inputs.get(src) or inputs.get("response"), classifier=fixture)
        return {out: decision}

register_worker("think.classify", _Think_Classify)
register_worker("lab.think.classify", _Think_Classify)
