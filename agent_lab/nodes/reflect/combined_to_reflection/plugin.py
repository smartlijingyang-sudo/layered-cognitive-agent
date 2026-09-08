"""reflect__combined_to_reflection — 1 in 1 out: combined -> Reflection (stub)."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="reflect__combined_to_reflection",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Critique combined inputs into a Reflection artifact (stub passthrough).",
    inputs=[PortInfo("combined", kind=PortKind.FACT)],
    outputs=[PortInfo("reflection", kind=PortKind.MANIFEST)],
)
class CombinedToReflection(Node):
    name = "reflect__combined_to_reflection"

    def execute(self, node, inputs):
        return {"reflection": inputs.get("combined")}
