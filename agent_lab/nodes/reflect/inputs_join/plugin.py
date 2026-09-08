"""reflect__inputs_join — 3 in 1 out: obs+dec+prior -> combined."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="reflect__inputs_join",
    layer=NodeLayer.PHASE,
    kind=NodeKind.ASSEMBLER,
    description="Combine observation + decision + prior reflection into one input (stub).",
    inputs=[
        PortInfo("observation", kind=PortKind.MANIFEST, required=False),
        PortInfo("decision", kind=PortKind.FACT, required=False),
        PortInfo("prior_reflection", kind=PortKind.MANIFEST, required=False),
    ],
    outputs=[PortInfo("combined", kind=PortKind.FACT)],
)
class InputsJoin(Node):
    name = "reflect__inputs_join"

    def execute(self, node, inputs):
        return {"combined": inputs.get("observation") or inputs.get("decision")}
