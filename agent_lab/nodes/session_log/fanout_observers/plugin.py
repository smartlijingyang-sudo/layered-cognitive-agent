"""session_log/fanout_observers — register an observer and trigger fan-out.

Registers a callable as a Session observer (called on every append) AND
returns a 'pump' handle. Calling pump pulls the latest batch of events
from the Session log and feeds them to the observer.

This is the explicit "consume" path for the runtime — the observer fires
synchronously inside Session.append; pump is the deferred-batch path.
"""
from __future__ import annotations
from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.fanout.observers",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Register an observer + provide a pump to fan-out Session events.",
    inputs=[PortInfo("observer", kind=PortKind.FACT)],
    outputs=[PortInfo("pump", kind=PortKind.FACT)],
)
class FanoutObservers(Node):
    name = "session_log.fanout.observers"

    def execute(self, node, inputs):
        from agent_lab.nodes.session_log._sink import get_session
        obs_a = inputs.get("observer")
        observer_fn = getattr(obs_a, "content", None) if obs_a else None
        if not callable(observer_fn):
            return {"pump": Artifact(kind=ArtifactKind.FACT, content={"registered": False},
                                       schema_ref="observer.pump.v1")}
        sess = session()
        # Register on Session so future appends fire it synchronously
        sess.observe(observer_fn)
        # Build a pump closure: call observer_fn on every event since last pump
        last_seq = {"value": 0}

        def _pump():
            current = sess.seq
            if current <= last_seq["value"]:
                return {"pumped": 0, "from_seq": last_seq["value"]}
            events = sess.snapshot_events(from_seq=last_seq["value"], to_seq_exclusive=current)
            for ev in events:
                try:
                    observer_fn(sess, ev)
                except Exception:
                    pass
            last_seq["value"] = current
            return {"pumped": len(events), "from_seq": last_seq["value"]}

        return {"pump": Artifact(
            kind=ArtifactKind.FACT,
            content={"registered": True, "pump": _pump,
                      "invoke": "call pump() to fan-out pending events"},
            schema_ref="observer.pump.v1",
        )}
