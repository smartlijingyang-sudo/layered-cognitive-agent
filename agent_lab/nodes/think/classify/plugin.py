"""think.classify — pure transform: LLMResponse → Decision.

Logic lives in ``ops.py`` (node purity: plugin.py has no data branching).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.nodes.think.classify.ops import classify_response


@node(
    id="think.classify",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Classify LLMResponse into a Decision via DefaultDecisionClassifier; "
        "map use_tool → call_tool for act."
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
        src = node.config.get("from", "response")
        out = node.config.get("to", "decision")
        response_artifact = inputs.get(src) or inputs.get("response")
        fixture = (node.config.get("provider_config") or {}).get("fixture_classifier")
        decision = classify_response(response_artifact, classifier=fixture)
        return {out: decision}
