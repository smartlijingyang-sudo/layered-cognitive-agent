"""think.classify — pure transform: LLMResponse → Decision.

No LLM call. Provider selection is data (LcaThinkParseProvider).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="think.classify",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Parse an LLMResponse-shaped artifact into a Decision "
        "(action_type ∈ {respond, call_tool, refuse})."
    ),
    inputs=[PortInfo("response", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("decision", kind=PortKind.FACT)],
    provides=["decision"],
    requires=["llm_response"],
    emits=["decision"],
    relates_to=["think.reason", "think.guard"],
)
class ThinkClassify(Node):
    name = "think.classify"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_think import LcaThinkParseProvider

        provider = LcaThinkParseProvider.from_node_config(node.config)
        src = node.config.get("from", "response")
        out = node.config.get("to", "decision")
        response_artifact = inputs.get(src) or inputs.get("response")
        if response_artifact is None:
            response_artifact = Artifact(kind=ArtifactKind.MESSAGE, content="")
        parsed = provider.parse(response_artifact)
        decision = parsed.get("decision")
        if decision is None:
            raise ValueError("think.classify: parser returned no decision artifact")
        return {out: decision}
