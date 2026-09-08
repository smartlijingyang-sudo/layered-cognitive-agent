"""think__prompt_assemble — 1 in 1 out: messages list -> prompt string.

The single point that flattens OpenAI-style message list into the
prompt string the LLMAdapter expects. Stays close to the adapter
contract; call_llm doesn't do this.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="think__prompt_assemble",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Flatten message list to prompt string with [role] prefixes.",
    inputs=[PortInfo("messages", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("prompt", kind=PortKind.TEXT)],
)
class PromptAssemble(Node):
    name = "think__prompt_assemble"

    def execute(self, node, inputs):
        msg_a = inputs.get("messages")
        messages = msg_a.content if msg_a else []
        if not isinstance(messages, list):
            messages = []
        sep = node.config.get("sep", "\n")
        parts = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            parts.append(f"[{m.get('role','user')}] {m.get('content','')}")
        return {"prompt": msg_a.__class__(kind=msg_a.kind, content=sep.join(parts), schema_ref="prompt.text.v1") if msg_a else None}
