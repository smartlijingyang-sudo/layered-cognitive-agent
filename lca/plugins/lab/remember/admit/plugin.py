# PR-D final 2/2 — remember.admit real @plugin carrier
"""Real carrier for ``agent_lab.nodes.remember.admit.plugin.RememberAdmit``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``RememberAdmit`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.remember.admit``
Output capability: ``lab.remember.admit.out:fact``

delete-when (PR-D final 2/2):
- agent_lab/nodes/remember/admit/plugin.py replaced by this carrier
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
    id="lab.remember.admit",
    stage="remember",
    kind="PRODUCER",
    description='Decide which facts to admit to the journal.',
    node_id='admit',
    source_module='agent_lab.nodes.remember.admit.plugin',
    source_class='RememberAdmit',
    provides=['remembered_fact'],
    requires=[],
    emits=['remembered_fact'],
    inputs=[('reflection', 'FACT', False)],
    outputs=[('fact', 'FACT')],
    out_capabilities=['lab.remember.admit.out:fact'],
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


# Auto-bind on import so the loader walks these like any other plugin
# carrier — the setup() function is still callable from a real Cordis
# boot path for two-phase register.
bind_carrier(_CARRIER)


__all__ = ["setup", "_CARRIER"]
