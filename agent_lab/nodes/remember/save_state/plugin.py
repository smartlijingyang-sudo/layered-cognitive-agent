"""save_state — call StateStore.save via LcaRememberStateStoreProvider.

Reads journal_fact from the upstream write_journal, derives a state dict,
and calls StateStore.save(state) -> str. Emits state_ref (the ref returned
by the store) and remember_signal (barrier signal for downstream phases).

Provider selection is data, not code; see
    agent_lab/graphs/configs/remember.yaml for the canonical call site.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)


@node(
    id="save_state",
    name="save_state",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description=(
        "Persist the AgentState snapshot via StateStore.save and emit "
        "a state_ref + remember_signal so downstream phases can fire."
    ),
    inputs=[PortInfo("journal_fact", kind=PortKind.FACT, required=False)],
    outputs=[
        PortInfo("state_ref", kind=PortKind.FACT),
        PortInfo("remember_signal", kind=PortKind.FACT),
    ],
    provides=["state_ref", "remember_signal"],
    requires=["state_store"],
    emits=["state_ref", "remember_signal"],
    relates_to=["write_journal"],
)
class SaveStateNode(Node):
    """Bridge journal_fact → StateStore.save via LcaRememberStateStoreProvider."""

    name = "save_state"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_memory import LcaRememberStateStoreProvider

        provider = LcaRememberStateStoreProvider.from_node_config(node.config)
        return provider.save_state(
            journal_fact_artifact=inputs.get("journal_fact"),
        )
