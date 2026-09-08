"""perceive.sense.tool_results — land prior-turn tool results into AgentState.

Single-responsibility: ONE list of tool result messages -> state.tool_results
field. Chain-style: 2 inputs (state, tool_results), 1 output.

Each tool result message is OpenAI-style {role: "tool", tool_call_id, content}.
Attachments inside content (multimodal tool outputs) are preserved verbatim
as part of the message. We don't pull attachments out — Hub reads
state.tool_results directly when constructing tool-role ContextItems.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.sense.tool_results",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Land prior-turn tool result messages (incl. attachments) into state.tool_results; append to state.history.",
    inputs=[
        PortInfo("state", kind=PortKind.FACT),
        PortInfo("tool_results", kind=PortKind.MESSAGE),
    ],
    outputs=[PortInfo("state", kind=PortKind.FACT)],
)
class SenseToolResults(Node):
    name = "perceive.sense.tool_results"

    def execute(self, node, inputs):
        state_a = inputs.get("state")
        tr_a = inputs.get("tool_results")
        if tr_a is None:
            return {"state": state_a}

        if state_a and isinstance(state_a.content, dict):
            base = dict(state_a.content)
        else:
            base = {}

        tr_content = tr_a.content
        # Normalize to a list of messages (one entry per tool call).
        if isinstance(tr_content, list):
            tool_msgs = [m for m in tr_content if isinstance(m, dict)]
        elif isinstance(tr_content, dict):
            tool_msgs = [tr_content]
        else:
            return {"state": state_a}  # unrecognized shape — passthrough

        base["tool_results"] = tool_msgs

        # Append to state.history so Hub sees the full conversation.
        history = base.get("history") or []
        if not isinstance(history, list):
            history = []
        base["history"] = list(history) + tool_msgs

        return {"state": Artifact(
            kind=ArtifactKind.FACT,
            content=base,
            schema_ref="agent_state.v1",
        )}
