"""model_visible__history_attach — 2 in 1 out: attach folded history to current messages."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="model_visible__history_attach",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.ASSEMBLER,
    description="Attach Session-derived history to the current messages list (history-as-SSOT).",
    inputs=[
        PortInfo("messages", kind=PortKind.MESSAGE),
        PortInfo("history", kind=PortKind.MESSAGE),
    ],
    outputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
)
class HistoryAttach(Node):
    name = "model_visible__history_attach"

    def execute(self, node, inputs):
        msgs_a = inputs.get("messages")
        hist_a = inputs.get("history")
        msgs = msgs_a.content if (msgs_a and isinstance(msgs_a.content, list)) else []
        hist = hist_a.content if (hist_a and isinstance(hist_a.content, list)) else []
        merged = hist + msgs
        return {"messages": msgs_a.__class__(kind=msgs_a.kind, content=merged, schema_ref=msgs_a.schema_ref) if msgs_a else None}
