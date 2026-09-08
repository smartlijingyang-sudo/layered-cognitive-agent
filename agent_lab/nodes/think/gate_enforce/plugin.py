"""think__gate_enforce — 1 in 1 out: Decision + state -> enforced Decision."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="think__gate_enforce",
    layer=NodeLayer.PHASE,
    kind=NodeKind.VALIDATOR,
    description="Apply DecisionGate.enforce (ChainedDecisionGate) — stub passthrough.",
    inputs=[PortInfo("decision", kind=PortKind.FACT)],
    outputs=[PortInfo("enforced_decision", kind=PortKind.FACT)],
)
class GateEnforce(Node):
    name = "think__gate_enforce"

    def execute(self, node, inputs):
        return {"enforced_decision": inputs.get("decision")}
