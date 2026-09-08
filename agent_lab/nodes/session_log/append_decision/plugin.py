"""session_log/append_decision — append a Decision artifact to the Session log.

Single-responsibility: one Decision -> one Session.append("decision.v1", ...) call.
Returns the seq + id of the resulting SessionEvent so callers can reference it.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.append.decision",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Append a Decision artifact to the Session log (event_type=decision.v1).",
    inputs=[PortInfo("decision", kind=PortKind.FACT)],
    outputs=[PortInfo("seq_ref", kind=PortKind.FACT)],
    provides=["session_seq_ref"],
)
class AppendDecision(Node):
    name = "session_log.append.decision"

    def execute(self, node, inputs):
        from agent_lab.nodes.session_log._sink import get_session
        decision_a = inputs.get("decision")
        if decision_a is None:
            return {"seq_ref": Artifact(kind=ArtifactKind.FACT, content={"seq": -1, "id": ""},
                                         schema_ref="session.seq_ref.v1")}
        sess = session()
        event = sess.append("decision.v1", _content_to_dict(decision_a.content))
        return {"seq_ref": Artifact(
            kind=ArtifactKind.FACT,
            content={"seq": event.seq, "id": getattr(event, "id", "")},
            schema_ref="session.seq_ref.v1",
        )}


def _content_to_dict(content):
    if isinstance(content, dict):
        return dict(content)
    return {"raw": content}
