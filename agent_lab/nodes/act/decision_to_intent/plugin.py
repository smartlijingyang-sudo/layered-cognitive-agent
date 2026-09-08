"""act__decision_to_intent — 1 in 1 out: Decision(call_tool) -> ToolIntent (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="act__decision_to_intent",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.PRODUCER,
    description="Extract ToolIntent from a call_tool Decision (stub passthrough).",
    inputs=[PortInfo("decision", kind=PortKind.FACT)],
    outputs=[PortInfo("intent", kind=PortKind.INTENT)],
)
class DecisionToIntent(Node):
    name = "act__decision_to_intent"

    def execute(self, node, inputs):
        return {"intent": inputs.get("decision")}
