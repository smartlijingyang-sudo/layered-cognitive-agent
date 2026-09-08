"""remember.snapshot — StateStore.save + remember_signal barrier.

Persists an AgentState snapshot derived from journal_fact. Emits state_ref
and remember_signal so downstream phases can fire.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember.snapshot",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=("Persist AgentState via StateStore.save; emit state_ref and remember_signal."),
    inputs=[PortInfo("journal_fact", kind=PortKind.FACT, required=False)],
    outputs=[
        PortInfo("state_ref", kind=PortKind.FACT),
        PortInfo("remember_signal", kind=PortKind.FACT),
    ],
    provides=["state_ref", "remember_signal"],
    requires=["state_store"],
    emits=["state_ref", "remember_signal"],
    relates_to=["remember.commit"],
)
class RememberSnapshot(Node):
    name = "remember.snapshot"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_memory import LcaRememberStateStoreProvider

        provider = LcaRememberStateStoreProvider.from_node_config(
            getattr(node, "config", None) or {}
        )
        return provider.save_state(
            journal_fact_artifact=inputs.get("journal_fact"),
        )
