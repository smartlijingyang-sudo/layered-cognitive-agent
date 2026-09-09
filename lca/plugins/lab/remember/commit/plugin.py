# PR-D final 2/2 — remember.commit real @plugin carrier
"""Real carrier for ``agent_lab.nodes.remember.commit.plugin.RememberCommit``.

Mirrors the LCA ``@plugin`` decorator contract (id / provides / requires /
emits / effects / contract / setup) without importing ``cordis`` at module
top. The actual ``RememberCommit`` class is imported lazily inside ``setup()`` so the
cordis chain (which the legacy class transitively pulls in) is only
triggered when the carrier is actually registered with a live Cordis
Context, not when the loader walks plugin modules.

Slot id: ``lab.remember.commit``
Output capability: ``lab.remember.commit.out:remembered``

delete-when (PR-D final 2/2):
- agent_lab/nodes/remember/commit/plugin.py replaced by this carrier
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
    id="lab.remember.commit",
    stage="remember",
    kind="EXECUTOR",
    description='Commit the admitted fact to the journal via Session.append.',
    node_id='commit',
    source_module='agent_lab.nodes.remember.commit.plugin',
    source_class='RememberCommit',
    provides=['remembered_artifact'],
    requires=[],
    emits=['remembered_artifact'],
    inputs=[('fact', 'FACT', False)],
    outputs=[('remembered', 'FACT')],
    out_capabilities=['lab.remember.commit.out:remembered'],
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

class _Remember_Commit(Worker):
    factory = "remember.commit"

    def execute(self, node, inputs, seams=None):
        from lca.plugins.lab.memory.ops import LcaRememberJournalProvider
        provider = LcaRememberJournalProvider.from_node_config(getattr(node, "config", None) or {})
        out_port = (getattr(node, "config", None) or {}).get("to", "journal_fact")
        return provider.append_journal(
            reflection_artifact=inputs.get("in_reflection"),
            observation_artifact=inputs.get("in_observation"),
            decision_artifact=inputs.get("in_decision"),
            admitted_artifact=inputs.get("admitted"),
            out_port=out_port,
        )

register_worker("remember.commit", _Remember_Commit)
register_worker("lab.remember.commit", _Remember_Commit)
