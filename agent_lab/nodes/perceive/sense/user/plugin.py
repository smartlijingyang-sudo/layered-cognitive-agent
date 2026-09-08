"""perceive.sense.user — write a user message into AgentState.user_input.

Single-responsibility: ONE user message -> ONE state field (user_input).
Chain-style: 2 inputs (state, user_message), 1 output (state with
user_input set).

The user message here is the FULL OpenAI-style message, not just text:
  {role: "user", content: <text or list of parts>, tool_calls?, ...}

Attachments (list of content parts like images / files) are preserved
verbatim. We don't pull attachments out — Hub reads state.user_input
as-is when constructing ContextItems.

The "history" record: every prior user message is appended to
state.history (list[dict]) so the Hub can fold prior turns too.
state.user_input is the LATEST message; state.history is the past.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="perceive.sense.user",
    layer=NodeLayer.MODEL_VISIBLE,
    kind=NodeKind.TRANSFORMER,
    description="Land the current user message (full OpenAI message shape, incl. attachments) into state.user_input; append to state.history.",
    inputs=[
        PortInfo("state", kind=PortKind.FACT),
        PortInfo("user_message", kind=PortKind.MESSAGE),
    ],
    outputs=[PortInfo("state", kind=PortKind.FACT)],
)
class SenseUser(Node):
    name = "perceive.sense.user"

    def execute(self, node, inputs):
        state_a = inputs.get("state")
        msg_a = inputs.get("user_message")
        if msg_a is None:
            return {"state": state_a}  # passthrough — nothing to write

        # Base state: may be empty for first turn
        if state_a and isinstance(state_a.content, dict):
            base = dict(state_a.content)
        else:
            base = {}

        # 1) Preserve FULL message shape (role / content / tool_calls / name / ...)
        #    Hub reads state.user_input directly.
        msg_content = msg_a.content if msg_a.content is not None else {}
        base["user_input"] = msg_content

        # 2) Maintain state.history (rolling log of all prior messages).
        history = base.get("history") or []
        if not isinstance(history, list):
            history = []
        # Append this turn's user message (only if it's a valid message dict)
        if isinstance(msg_content, dict) and msg_content.get("role"):
            history = list(history) + [msg_content]
        elif isinstance(msg_content, list):
            # Edge case: caller passed a list of messages (multi-input)
            history = list(history) + [m for m in msg_content if isinstance(m, dict)]
        base["history"] = history

        return {"state": Artifact(
            kind=ArtifactKind.FACT,
            content=base,
            schema_ref="agent_state.v1",
        )}
