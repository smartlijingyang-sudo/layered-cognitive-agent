"""act__intent_dispatch — 1 in 1 out: ToolIntent -> EffectReceipt (stub).

Real impl wraps SimpleSafeExecutor.execute(tool, args).
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="act__intent_dispatch",
    layer=NodeLayer.EFFECT,
    kind=NodeKind.EXECUTOR,
    description="Dispatch ToolIntent via SimpleSafeExecutor; emit EffectReceipt (stub).",
    inputs=[PortInfo("intent", kind=PortKind.INTENT)],
    outputs=[PortInfo("receipt", kind=PortKind.RECEIPT)],
)
class IntentDispatch(Node):
    name = "act__intent_dispatch"

    def execute(self, node, inputs):
        return {"receipt": inputs.get("intent")}
