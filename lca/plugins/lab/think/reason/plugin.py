# PR-D final 2/2 — think.reason real @plugin carrier
"""Real carrier for ``agent_lab.nodes.think.reason.plugin.ThinkReason``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ThinkReason`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.think.reason``
Output capability: ``lab.think.reason.out:response``

delete-when (PR-D final 2/2):
- agent_lab/nodes/think/reason/plugin.py replaced by this carrier
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
    id="lab.think.reason",
    stage="think",
    kind="EXECUTOR",
    description='Call OpenAICompatAdapter.complete on exposed messages.',
    node_id='reason',
    source_module='agent_lab.nodes.think.reason.plugin',
    source_class='ThinkReason',
    provides=['llm_response'],
    requires=['think_messages'],
    emits=['llm_call'],
    inputs=[('messages', 'MESSAGE', False), ('tools', 'FACT', False)],
    outputs=[('response', 'MESSAGE')],
    out_capabilities=['lab.think.reason.out:response'],
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

class _Think_Reason(Worker):
    factory = "think.reason"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.think.reason.ops import complete_turn
        from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter
        src = node.config.get("from", "messages")
        out = node.config.get("to", "response")
        response = complete_turn(
            inputs.get(src) or inputs.get("messages"),
            inputs.get("tools"),
            adapter_factory=OpenAICompatAdapter,
            adapter_kwargs=dict(node.config.get("adapter_kwargs", {}) or {})
        )
        return {out: response}

register_worker("think.reason", _Think_Reason)
register_worker("lab.think.reason", _Think_Reason)
