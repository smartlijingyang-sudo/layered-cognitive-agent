"""session_log/register_observer — register an observer callable to the Session.

Observers are called on every Session.append; they are the mechanism
for fan-out to durable sinks (JSONL writer, OTLP exporter, etc.). The
returned cancel callable de-registers the observer (idempotent).
"""
from __future__ import annotations

from typing import Any

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.register.observer",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Register an observer callable to the Session; return cancel handle.",
    inputs=[PortInfo("observer", kind=PortKind.FACT)],
    outputs=[PortInfo("cancel", kind=PortKind.FACT)],
    provides=["observer_cancel"],
)
class RegisterObserver(Node):
    name = "session_log.register.observer"

    def execute(self, node, inputs):
        from agent_lab._session_holder import session
        obs_a = inputs.get("observer")
        if obs_a is None or not callable(getattr(obs_a, "content", None)):
            return {"cancel": Artifact(kind=ArtifactKind.FACT, content={"registered": False},
                                         schema_ref="observer.cancel.v1")}
        observer_fn: Any = obs_a.content
        sess = session()
        cancel = sess.observe(observer_fn)
        return {"cancel": Artifact(
            kind=ArtifactKind.FACT,
            content={"registered": True, "cancel": cancel},
            schema_ref="observer.cancel.v1",
        )}
