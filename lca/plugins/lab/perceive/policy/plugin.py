# PR-D final 2/2 — perceive.policy real @plugin carrier
"""Real carrier for ``agent_lab.nodes.perceive.policy.plugin.PerceivePolicy``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``PerceivePolicy`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.perceive.policy``
Output capability: ``lab.perceive.policy.out:policy``

delete-when (PR-D final 2/2):
- agent_lab/nodes/perceive/policy/plugin.py replaced by this carrier
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
    id="lab.perceive.policy",
    stage="perceive",
    kind="VALIDATOR",
    description='Apply the perceive guard policy to sensor resolution.',
    node_id='policy',
    source_module='agent_lab.nodes.perceive.policy.plugin',
    source_class='PerceivePolicy',
    provides=['policy'],
    requires=['sensors'],
    emits=['policy'],
    inputs=[('sensors', 'FACT', False), ('state', 'FACT', False)],
    outputs=[('policy', 'FACT')],
    out_capabilities=['lab.perceive.policy.out:policy'],
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


# Auto-bind on import so the loader walks these like any other plugin
# carrier — the setup() function is still callable from a real Cordis
# boot path for two-phase register.
bind_carrier(_CARRIER)


__all__ = ["setup", "_CARRIER"]
