# PR-D final 2/2 — model_eye.trust_classify real @plugin carrier
"""Real carrier for ``agent_lab.nodes.model_eye.trust_classify.plugin.TrustClassify``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``TrustClassify`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.model_eye.trust_classify``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/model_eye/trust_classify/plugin.py replaced by this carrier
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
    id="lab.model_eye.trust_classify",
    stage="model_eye",
    kind="VALIDATOR",
    description='Tag tool results with a trust classification.',
    node_id='trust_classify',
    source_module='agent_lab.nodes.model_eye.trust_classify.plugin',
    source_class='TrustClassify',
    provides=[],
    requires=[],
    emits=[],
    inputs=[('results', 'FACT', False)],
    outputs=[('trust_labels', 'FACT')],
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
