"""parse_decision_node — turn an LLM response into a Decision.

Pure transform bridge. Reads an LLMResponse artifact (text + tool_calls),
emits a Decision artifact with action_type ∈ {respond, call_tool, refuse}.

The LLM call itself lives in the upstream ``call_llm`` node; this node
only does parsing. Provider selection is data, not code.
see
    agent_lab/graphs/configs/think.yaml for the canonical call site.
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)
from agent_lab.primitives.artifact import Artifact


@node(
    id="parse_decision_node",
    name="parse_decision_node",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Parse an LLMResponse artifact into a Decision artifact. Used in "
        "the think sub-graph to bridge the LLM call output into the LCA "
        "Decision contract."
    ),
    inputs=[PortInfo("response", kind=PortKind.MESSAGE, required=False)],
    outputs=[PortInfo("decision", kind=PortKind.FACT)],
    provides=["decision"],
    requires=["llm_response"],
    emits=["decision"],
    relates_to=["call_llm", "gate_enforce_node"],
)
class ParseDecisionNode(Node):
    """Bridge LLM response → Decision via LcaThinkParseProvider."""

    name = "parse_decision_node"

    def execute(self, node, inputs):
        from agent_lab.adapters.lca_think import LcaThinkParseProvider

        provider = LcaThinkParseProvider.from_node_config(node.config)
        out_port = node.config.get("to", node.outs[0] if node.outs else "decision")
        response_artifact = inputs.get("response") or Artifact(kind="message", content="")
        return {out_port: provider.parse(response_artifact)[out_port]}
