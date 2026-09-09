# PR-D final 2/2 — control.route_on real @plugin carrier
"""Real carrier for ``agent_lab.plugins.semantic_router.SemanticRouterPlugin``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``SemanticRouterPlugin`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.control.route_on``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/control/route_on/plugin.py replaced by this carrier
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
    id="lab.control.route_on",
    stage="control",
    kind="ROUTER",
    description='Route a node output to one of several downstream paths by predicate.',
    node_id='route_on',
    source_module='agent_lab.plugins.semantic_router',
    source_class='SemanticRouterPlugin',
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

class _RouteOn(Worker):
    factory = "route_on"

    def execute(self, node, inputs, seams=None):
        from agent_lab.primitives.artifact import Artifact, ArtifactKind
        key_in = node.config["key_from"]
        table: dict = node.config["table"]
        out_port = node.outs[0]
        key_a = inputs.get(key_in)
        if key_a is None:
            return {out_port: Artifact(kind=ArtifactKind.FACT, content={"routed": None})}
        key = str(key_a.content) if not isinstance(key_a.content, dict) else str(key_a.content.get("verdict", ""))
        chosen_in = table.get(key, node.config.get("default"))
        if chosen_in is None or chosen_in not in inputs:
            return {out_port: Artifact(kind=ArtifactKind.INTENT, content={"tool": "__none__", "args": {}, "verdict": "deny"}, schema_ref="tool.intent.v1")}
        chosen = inputs[chosen_in]
        return {out_port: chosen.model_copy(update={"content": {**chosen.content, "routed_via": key}})}

register_worker("route_on", _RouteOn)
register_worker("lab.route_on", _RouteOn)
