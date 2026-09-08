"""remember__append_observation — 1 in 1 out: observation -> session_event(seq) (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember__append_observation",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Append observation to Session — stub.",
    inputs=[PortInfo("observation", kind=PortKind.MANIFEST)],
    outputs=[PortInfo("seq", kind=PortKind.FACT)],
)
class AppendObservation(Node):
    name = "remember__append_observation"

    def execute(self, node, inputs):
        return {"seq": inputs.get("observation")}
