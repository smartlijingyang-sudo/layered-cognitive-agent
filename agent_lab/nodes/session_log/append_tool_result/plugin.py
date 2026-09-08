"""session_log/append_tool_result — append a {role:tool} message to the Session log.

The tool result is a single message (per OpenAI chat format) — appending
it to the log closes the model-visible history loop (next turn sees it
via fold_messages).
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log__append_tool_result",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Append a {role:tool} message to the Session log (event_type=tool.result.v1).",
    inputs=[PortInfo("tool_message", kind=PortKind.MESSAGE)],
    outputs=[PortInfo("seq_ref", kind=PortKind.FACT)],
    provides=["session_seq_ref"],
)
class AppendToolResult(Node):
    name = "session_log__append_tool_result"

    def execute(self, node, inputs):
        from agent_lab._session_holder import session
        msg_a = inputs.get("tool_message")
        if msg_a is None:
            return {"seq_ref": Artifact(kind=ArtifactKind.FACT, content={"seq": -1, "id": ""},
                                         schema_ref="session.seq_ref.v1")}
        sess = session()
        event = sess.append("tool.result.v1", _content_to_dict(msg_a.content))
        return {"seq_ref": Artifact(
            kind=ArtifactKind.FACT,
            content={"seq": event.seq, "id": getattr(event, "id", "")},
            schema_ref="session.seq_ref.v1",
        )}


def _content_to_dict(content):
    if isinstance(content, dict):
        return dict(content)
    return {"raw": content}
