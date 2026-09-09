# PR-D final 2/2 — llm.call_llm real @plugin carrier
"""Real carrier for ``agent_lab.nodes.llm.call_llm.plugin.CallLLM``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``CallLLM`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.llm.call_llm``
Output capability: ``(none)``

delete-when (PR-D final 2/2):
- agent_lab/nodes/llm/call_llm/plugin.py replaced by this carrier
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
    id="lab.llm.call_llm",
    stage="llm",
    kind="EXECUTOR",
    description='Call the LLM with assembled messages.',
    node_id='call_llm',
    source_module='agent_lab.nodes.llm.call_llm.plugin',
    source_class='CallLLM',
    provides=['llm_response'],
    requires=['llm_messages'],
    emits=[],
    inputs=[('messages', 'MESSAGE', False)],
    outputs=[('response', 'MESSAGE')],
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
