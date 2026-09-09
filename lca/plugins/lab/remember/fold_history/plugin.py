# PR-D final 2/2 — remember.fold_history real @plugin carrier
"""Real carrier for ``agent_lab.nodes.remember.fold_history.plugin.RememberFoldHistory``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``RememberFoldHistory`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.remember.fold_history``
Output capability: ``lab.remember.fold_history.out:history``

delete-when (PR-D final 2/2):
- agent_lab/nodes/remember/fold_history/plugin.py replaced by this carrier
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
    id="lab.remember.fold_history",
    stage="remember",
    kind="TRANSFORMER",
    description='Fold history of remembered facts into a digest.',
    node_id='fold_history',
    source_module='agent_lab.nodes.remember.fold_history.plugin',
    source_class='RememberFoldHistory',
    provides=['remembered_history'],
    requires=[],
    emits=['remembered_history'],
    inputs=[('remembered', 'FACT', False)],
    outputs=[('history', 'FACT')],
    out_capabilities=['lab.remember.fold_history.out:history'],
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


# Auto-bind on import so the loader walks these like any other plugin
# carrier — the setup() function is still callable from a real Cordis
# boot path for two-phase register.
bind_carrier(_CARRIER)


__all__ = ["setup", "_CARRIER"]
