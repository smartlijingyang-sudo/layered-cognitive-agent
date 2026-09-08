"""stop__stop_decide — 1 in 1 out: state+inputs -> StopDecision (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="stop__stop_decide",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="StopPolicy.decide -> StopDecision + terminal (stub passthrough).",
    inputs=[PortInfo("state", kind=PortKind.FACT)],
    outputs=[PortInfo("stop_decision", kind=PortKind.FACT)],
)
class StopDecide(Node):
    name = "stop__stop_decide"

    def execute(self, node, inputs):
        return {"stop_decision": inputs.get("state")}
