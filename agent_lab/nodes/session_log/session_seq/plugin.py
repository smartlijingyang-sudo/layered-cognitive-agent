"""session_log/session_seq — read the Session's next-event seq.

Single-responsibility: return the Session's monotonic seq counter
(equivalent to len(log)). Used by observability and checkpoint markers.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.session.seq",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.TRANSFORMER,
    description="Return the Session's next seq counter (= current log length).",
    inputs=[],
    outputs=[PortInfo("seq", kind=PortKind.FACT)],
    provides=["session_seq"],
)
class SessionSeq(Node):
    name = "session_log.session.seq"

    def execute(self, node, inputs):
        from agent_lab.nodes.session_log._sink import get_session
        sess = session()
        return {"seq": Artifact(
            kind=ArtifactKind.FACT,
            content={"seq": sess.seq, "session_id": sess.id},
            schema_ref="session.seq.v1",
        )}
