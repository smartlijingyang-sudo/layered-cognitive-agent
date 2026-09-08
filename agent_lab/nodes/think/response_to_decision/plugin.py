"""think__response_to_decision — 1 in 1 out: LLMResponse -> Decision (pure parse)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="think__response_to_decision",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Parse LLMResponse text + tool_calls into a Decision (stub: passthrough).",
    inputs=[PortInfo("response", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("decision", kind=PortKind.FACT)],
)
class ResponseToDecision(Node):
    name = "think__response_to_decision"

    def execute(self, node, inputs):
        return {"decision": inputs.get("response")}
