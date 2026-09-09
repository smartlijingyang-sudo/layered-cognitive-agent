# PR-D final 2/2 — think.guard real @plugin carrier
"""Real carrier for ``agent_lab.nodes.think.guard.plugin.ThinkGuard``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ThinkGuard`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.think.guard``
Output capability: ``lab.think.guard.out:decision, lab.think.guard.out:think_signal``

delete-when (PR-D final 2/2):
- agent_lab/nodes/think/guard/plugin.py replaced by this carrier
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
    id="lab.think.guard",
    stage="think",
    kind="VALIDATOR",
    description='Enforce DecisionGate over the decision.',
    node_id='guard',
    source_module='agent_lab.nodes.think.guard.plugin',
    source_class='ThinkGuard',
    provides=['think_decision'],
    requires=[],
    emits=['think_decision', 'think_signal'],
    inputs=[('decision', 'FACT', False), ('in_state', 'FACT', False)],
    outputs=[('decision', 'FACT'), ('think_signal', 'FACT')],
    out_capabilities=['lab.think.guard.out:decision', 'lab.think.guard.out:think_signal'],
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

class _Think_Guard(Worker):
    factory = "think.guard"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.think.guard.ops import enforce_decision
        cfg = dict(node.config or {})
        provider_cfg = dict(cfg.get("provider_config") or {})
        merged = {**provider_cfg, **{k: cfg[k] for k in ("null_gate","gate_factory","fixture_gate_name","allow_empty_chain","gate") if k in cfg}}
        src = cfg.get("from", "decision")
        out = cfg.get("to", "enforced_decision")
        result = enforce_decision(inputs.get(src) or inputs.get("decision"), inputs.get("in_state"), config=merged, out_port=out)
        ports = node.outs or [out, "think_signal"]
        return {port: result.get(port, Artifact(kind=ArtifactKind.FACT, content=None)) for port in ports}

register_worker("think.guard", _Think_Guard)
register_worker("think.guard", _Think_Guard)
register_worker("lab.think.guard", _Think_Guard)
