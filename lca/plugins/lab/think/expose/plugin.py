# PR-D final 2/2 — think.expose real @plugin carrier
"""Real carrier for ``agent_lab.nodes.think.expose.plugin.ThinkExpose``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``ThinkExpose`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.think.expose``
Output capability: ``lab.think.expose.out:messages, lab.think.expose.out:tools``

delete-when (PR-D final 2/2):
- agent_lab/nodes/think/expose/plugin.py replaced by this carrier
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
    id="lab.think.expose",
    stage="think",
    kind="TRANSFORMER",
    description='Extract messages + tools from a committed ContextManifest.',
    node_id='expose',
    source_module='agent_lab.nodes.think.expose.plugin',
    source_class='ThinkExpose',
    provides=['think_messages', 'think_tools'],
    requires=['context_manifest'],
    emits=['think_messages', 'think_tools'],
    inputs=[('in_assembled_manifest', 'MANIFEST', False), ('in_state', 'FACT', False)],
    outputs=[('messages', 'MESSAGE'), ('tools', 'FACT')],
    out_capabilities=['lab.think.expose.out:messages', 'lab.think.expose.out:tools'],
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

class _Think_Expose(Worker):
    factory = "think.expose"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.think.expose.ops import peel_manifest
        src = node.config.get("from", "in_assembled_manifest")
        peeled = peel_manifest(inputs.get(src) or inputs.get("in_assembled_manifest"))
        msg_out = node.config.get("to", "messages")
        tools_out = node.config.get("tools_to", "tools")
        return {msg_out: peeled["messages"], tools_out: peeled["tools"]}

register_worker("think.expose", _Think_Expose)
register_worker("lab.think.expose", _Think_Expose)
