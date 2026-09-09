# PR-D final 2/2 — model_eye.see real @plugin carrier
"""Real carrier for ``agent_lab.nodes.model_eye.see.plugin.ModelEyeSee``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ModelEyeSee`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.model_eye.see``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/model_eye/see/plugin.py replaced by this carrier
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
    id="lab.model_eye.see",
    stage="model_eye",
    kind="TRANSFORMER",
    description='Project the model-visible input bundle into a Manifest.',
    node_id='see',
    source_module='agent_lab.nodes.model_eye.see.plugin',
    source_class='ModelEyeSee',
    provides=['model_visible_manifest'],
    requires=[],
    emits=[],
    inputs=[('messages', 'MESSAGE', False), ('tools', 'FACT', False), ('results', 'FACT', False)],
    outputs=[('manifest', 'MANIFEST')],
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
