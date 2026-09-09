# PR-D final 2/2 — control.think_guard real @plugin carrier
"""Real carrier for ``agent_lab.nodes.control.think_guard.plugin.ThinkGuardNode``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ThinkGuardNode`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.control.think_guard``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/control/think_guard/plugin.py replaced by this carrier
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
    id="lab.control.think_guard",
    stage="control",
    kind="VALIDATOR",
    description='Control-plane wrapper around the think guard validator.',
    node_id='think_guard',
    source_module='agent_lab.nodes.control.think_guard.plugin',
    source_class='ThinkGuardNode',
    provides=['think_guard_control'],
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

class _ThinkGuardNode(Worker):
    factory = "think_guard_node"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.control.think_guard.ops import handle_control_decision
        cfg = node.config or {}
        provider_cfg = dict(cfg.get("provider_config") or {})
        mode = str(provider_cfg.get("mode") or cfg.get("mode") or "passthrough")
        out_port = cfg.get("to", "out_decision")
        enforce_cfg = {k: v for k, v in provider_cfg.items() if k != "mode"}
        return handle_control_decision(inputs.get("in_decision"), mode=mode, out_port=out_port, enforce_config=enforce_cfg)

register_worker("think_guard_node", _ThinkGuardNode)
register_worker("think_guard", _ThinkGuardNode)
register_worker("lab.think_guard_node", _ThinkGuardNode)
