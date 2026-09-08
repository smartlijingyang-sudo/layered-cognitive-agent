"""session_log/snapshot_events — return recent Session events as an immutable tuple.

Single-responsibility: read [from_seq, to_seq_exclusive) from the Session
log. Default config: from_seq=0, limit=1000 (tail). Use the agent_lab
config block to constrain the window (e.g. last 50 events for dashboards).
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.snapshot.events",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.TRANSFORMER,
    description="Snapshot recent Session events (config.from_seq, config.limit).",
    inputs=[],
    outputs=[PortInfo("events", kind=PortKind.FACT)],
    provides=["session_events_snapshot"],
)
class SnapshotEvents(Node):
    name = "session_log.snapshot.events"

    def execute(self, node, inputs):
        from agent_lab.nodes.session_log._sink import get_session
        sess = session()
        from_seq = int(node.config.get("from_seq", 0))
        limit = int(node.config.get("limit", 1000))
        # Snapshot [from_seq, from_seq+limit); clamp end to log length
        # (LCA raises ValueError on out-of-range to_seq_exclusive).
        end = min(from_seq + limit, sess.seq)
        events = sess.snapshot_events(from_seq=from_seq, to_seq_exclusive=end) if end > from_seq else ()
        return {"events": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": [_event_to_dict(e) for e in events],
                      "from_seq": from_seq, "limit": limit, "count": len(events)},
            schema_ref="session.events_snapshot.v1",
        )}


def _event_to_dict(event):
    return {
        "seq": getattr(event, "seq", -1),
        "id": getattr(event, "id", ""),
        "type": getattr(event, "type", ""),
        "data": getattr(event, "data", {}),
        "time": getattr(event, "time", 0),
        "actor": getattr(event, "actor", None),
        "visibility": getattr(event, "visibility", "model"),
    }
