"""session_log/append_checkpoint — append a checkpoint marker to the Session log.

Used by long-running loops to mark durable progress; observability
infrastructure (lineage/observer) consumes these to drive state stores.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.append.checkpoint",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Append a checkpoint marker to the Session log (event_type=checkpoint.v1).",
    inputs=[PortInfo("checkpoint", kind=PortKind.FACT)],
    outputs=[PortInfo("seq_ref", kind=PortKind.FACT)],
    provides=["session_seq_ref"],
)
class AppendCheckpoint(Node):
    name = "session_log.append.checkpoint"

    def execute(self, node, inputs):
        from agent_lab.nodes.session_log._sink import get_session
        ck_a = inputs.get("checkpoint")
        data = _content_to_dict(ck_a.content) if ck_a else {}
        sess = session()
        event = sess.append("checkpoint.v1", data)
        return {"seq_ref": Artifact(
            kind=ArtifactKind.FACT,
            content={"seq": event.seq, "id": getattr(event, "id", "")},
            schema_ref="session.seq_ref.v1",
        )}


def _content_to_dict(content):
    if isinstance(content, dict):
        return dict(content)
    return {"raw": content}
