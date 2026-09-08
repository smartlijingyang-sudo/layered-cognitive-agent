"""session_log/append_node_end — emit a node_end framework event to Session."""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.append.node_end",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Emit a node_end framework event to Session (lifecycle tracing).",
    inputs=[PortInfo("event", kind=PortKind.FACT)],
    outputs=[PortInfo("seq_ref", kind=PortKind.FACT)],
)
class AppendNodeEnd(Node):
    name = "session_log.append.node_end"

    def execute(self, node, inputs):
        from agent_lab._session_holder import session
        ev_a = inputs.get("event")
        sess = session()
        data = _content_to_dict(ev_a.content) if ev_a else {}
        event = sess.append("graph.node_end.v1", data)
        return {"seq_ref": _seq_ref(event)}


def _content_to_dict(content):
    if isinstance(content, dict):
        return dict(content)
    return {"raw": content}


def _seq_ref(event):
    return Artifact(
        kind=ArtifactKind.FACT,
        content={"seq": event.seq, "id": getattr(event, "id", "")},
        schema_ref="session.seq_ref.v1",
    )
