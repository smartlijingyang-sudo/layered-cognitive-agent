"""session_log/consume_events — read Session events + apply a consumer function.

Pulls a window of events from the Session log and applies a registered
consumer callable to each one. The consumer is responsible for whatever
business work the event represents (logging, projection, side effect).

Output: a FACT artifact carrying per-event consumer results.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.consume.events",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Pull Session events and apply a consumer callable to each.",
    inputs=[
        PortInfo("consumer", kind=PortKind.FACT),
        PortInfo("events", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("results", kind=PortKind.FACT)],
)
class ConsumeEvents(Node):
    name = "session_log.consume.events"

    def execute(self, node, inputs):
        consumer_a = inputs.get("consumer")
        events_a = inputs.get("events")
        # If events not supplied, pull a default window from the Session
        if events_a is None:
            from agent_lab.nodes.session_log._sink import get_session
            sess = session()
            from_seq = int(node.config.get("from_seq", 0))
            limit = int(node.config.get("limit", 1000))
            end = min(from_seq + limit, sess.seq)
            events = sess.snapshot_events(from_seq=from_seq, to_seq_exclusive=end) if end > from_seq else ()
            events_list = [_event_to_dict(e) for e in events]
        else:
            events_list = events_a.content.get("items", []) if isinstance(events_a.content, dict) else []

        consumer_fn = getattr(consumer_a, "content", None) if consumer_a else None
        results: list = []
        if callable(consumer_fn):
            for ev in events_list:
                try:
                    res = consumer_fn(ev)
                except Exception as exc:  # containment boundary
                    res = {"error": str(exc), "seq": ev.get("seq", -1)}
                results.append(res)
        return {"results": Artifact(
            kind=ArtifactKind.FACT,
            content={"items": results, "count": len(results)},
            schema_ref="session.consume_results.v1",
        )}


def _event_to_dict(event):
    return {
        "seq": getattr(event, "seq", -1),
        "id": getattr(event, "id", ""),
        "type": getattr(event, "type", ""),
        "data": getattr(event, "data", {}),
        "time": getattr(event, "time", 0),
    }
