"""session_log/append_observation — append an Observation artifact to the Session log."""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.append.observation",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Append an Observation artifact to the Session log (event_type=observation.v1).",
    inputs=[PortInfo("observation", kind=PortKind.MANIFEST)],
    outputs=[PortInfo("seq_ref", kind=PortKind.FACT)],
    provides=["session_seq_ref"],
)
class AppendObservation(Node):
    name = "session_log.append.observation"

    def execute(self, node, inputs):
        from agent_lab._session_holder import session
        obs_a = inputs.get("observation")
        if obs_a is None:
            return {"seq_ref": Artifact(kind=ArtifactKind.FACT, content={"seq": -1, "id": ""},
                                         schema_ref="session.seq_ref.v1")}
        sess = session()
        event = sess.append("observation.v1", _content_to_dict(obs_a.content))
        return {"seq_ref": Artifact(
            kind=ArtifactKind.FACT,
            content={"seq": event.seq, "id": getattr(event, "id", "")},
            schema_ref="session.seq_ref.v1",
        )}


def _content_to_dict(content):
    if isinstance(content, dict):
        return dict(content)
    return {"raw": content}
