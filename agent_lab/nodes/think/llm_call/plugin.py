"""think__llm_call — 1 in 1 out: prompt string -> LLMResponse.

Wraps OpenAICompatAdapter.complete(prompt). No parsing, no Decision
construction — those belong to response_to_decision.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node


@node(
    id="think__llm_call",
    layer=NodeLayer.PHASE,
    kind=NodeKind.EXECUTOR,
    description="Call OpenAICompatAdapter.complete(prompt); emit LLMResponse (stub).",
    inputs=[PortInfo("prompt", kind=PortKind.TEXT)],
    outputs=[PortInfo("response", kind=PortKind.MESSAGE)],
)
class LLMCall(Node):
    name = "think__llm_call"

    def execute(self, node, inputs):
        return {"response": inputs.get("prompt")}
