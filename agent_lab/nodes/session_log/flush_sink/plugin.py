"""session_log/flush_sink — explicitly flush a registered sink's buffer.

In batched mode, the sink buffers events before appending to disk.
flush_sink drains the buffer synchronously and returns the count of
flushed events. Call this at end-of-turn / end-of-run / before close
to guarantee durability.

In simple mode (batch_size=1), each event is already flushed immediately;
calling flush_sink is a no-op (returns 0).
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.flush.sink",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Explicitly flush a registered sink's buffer to disk.",
    inputs=[PortInfo("name", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("result", kind=PortKind.FACT)],
    provides=["sink_flush_result"],
)
class FlushSink(Node):
    name = "session_log.flush.sink"

    def execute(self, node, inputs):
        name_a = inputs.get("name")
        sink_name = (name_a.content if name_a and isinstance(name_a.content, str) else None) \
                    or node.config.get("name", "default")
        # Look up via the Session (scoped registry, NOT process-global).
        from agent_lab.nodes.session_log._sink import get_session_sink, get_session
        # Ensure the Session-scoped registry is initialized
        _ = get_session()
        entry = get_session_sink(sink_name)
        if entry is None:
            return {"result": Artifact(
                kind=ArtifactKind.FACT,
                content={"flushed": False, "error": f"no sink registered on Session: {sink_name}"},
                schema_ref="sink.flush.v1",
            )}
        sink_instance, flush_fn = entry
        try:
            flush_fn()
        except Exception as exc:
            return {"result": Artifact(
                kind=ArtifactKind.FACT,
                content={"flushed": False, "error": str(exc)},
                schema_ref="sink.flush.v1",
            )}
        path = getattr(sink_instance, "path", None)
        return {"result": Artifact(
            kind=ArtifactKind.FACT,
            content={"flushed": True, "name": sink_name, "path": str(path) if path else None},
            schema_ref="sink.flush.v1",
        )}
