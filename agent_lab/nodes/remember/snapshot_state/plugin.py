"""remember__snapshot_state — 1 in 1 out: AgentState -> state_ref (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember__snapshot_state",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Snapshot AgentState via StateStore.save; emit state_ref (stub).",
    inputs=[PortInfo("state", kind=PortKind.FACT)],
    outputs=[PortInfo("state_ref", kind=PortKind.FACT)],
)
class SnapshotState(Node):
    name = "remember__snapshot_state"

    def execute(self, node, inputs):
        return {"state_ref": inputs.get("state")}
