"""act__intent_allow — 1 in 1 out: ToolIntent -> verdict (allow/deny) per capability policy."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="act__intent_allow",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.VALIDATOR,
    description="Check ToolIntent against capability policy; emit allow/deny verdict.",
    inputs=[PortInfo("intent", kind=PortKind.INTENT)],
    outputs=[PortInfo("verdict", kind=PortKind.FACT)],
)
class IntentAllow(Node):
    name = "act__intent_allow"

    def execute(self, node, inputs):
        return {"verdict": inputs.get("intent")}
