"""remember__fold_history — 1 in 1 out: Session -> messages list (pure fold).

Real impl: session.derive_messages() (per LCA projection fabric).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="remember__fold_history",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description="Fold Session log into OpenAI-style messages list (model-visible history SSOT).",
    inputs=[PortInfo("session", kind=PortKind.FACT)],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
)
class FoldHistory(Node):
    name = "remember__fold_history"

    def execute(self, node, inputs):
        return {"messages": inputs.get("session")}
