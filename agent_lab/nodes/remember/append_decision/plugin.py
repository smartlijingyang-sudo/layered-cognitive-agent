"""remember__append_decision — 1 in 1 out: Decision -> session_event(seq) (stub).

Real impl: session.append("decision.v1", decision.__dict__).
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember__append_decision",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Append Decision to Session (single fact-write seam) — stub.",
    inputs=[PortInfo("decision", kind=PortKind.FACT)],
    outputs=[PortInfo("seq", kind=PortKind.FACT)],
)
class AppendDecision(Node):
    name = "remember__append_decision"

    def execute(self, node, inputs):
        return {"seq": inputs.get("decision")}
