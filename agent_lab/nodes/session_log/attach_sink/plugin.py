"""session_log/attach_sink — attach a durable JSONL sink to the Session.

Single-responsibility: configure a JsonlFileSink and register it as a
Session observer so every event (domain fact OR framework lifecycle)
is appended to a JSONL file on disk.

Configuration (input port 'sink_config' FACT):
  {
    "path": "/path/to/events.jsonl",   # required
    "mode": "simple" | "batched",       # default "simple"
    "batch_size": 50,                   # default 1 (simple), 50 (batched)
    "fsync": false,                    # default False (production: True)
  }

The sink config can also be supplied via node.config (path / mode / etc.)
when the node is wired in a graph.

Returns a status FACT carrying the registered observer + cancel handle.
"""
from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import NodeKind, NodeLayer, PortInfo, PortKind, node
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="session_log.attach.sink",
    layer=NodeLayer.LINEAGE,
    kind=NodeKind.EXECUTOR,
    description="Attach a JSONL file sink to the Session (durable event log).",
    inputs=[PortInfo("sink_config", kind=PortKind.FACT, required=False)],
    outputs=[PortInfo("status", kind=PortKind.FACT)],
    provides=["session_sink_status"],
)
class AttachSink(Node):
    name = "session_log.attach.sink"

    def execute(self, node, inputs):
        from agent_lab.nodes.session_log._sink import get_session
        from pathlib import Path

        # Resolve config: input port wins, else node.config, else default
        cfg_a = inputs.get("sink_config")
        if cfg_a and isinstance(cfg_a.content, dict):
            cfg = dict(cfg_a.content)
        else:
            cfg = dict(node.config or {})

        path = cfg.get("path") or node.config.get("default_path")
        if path is None:
            return {"status": Artifact(
                kind=ArtifactKind.FACT,
                content={"attached": False, "error": "missing 'path' in sink_config"},
                schema_ref="sink.status.v1",
            )}
        mode = cfg.get("mode", "simple")
        batch_size = int(cfg.get("batch_size", 1 if mode == "simple" else 50))
        fsync = bool(cfg.get("fsync", False))

        try:
            from lca.infrastructure.persistence.jsonl_sink import JsonlFileSink
        except ImportError as exc:
            return {"status": Artifact(
                kind=ArtifactKind.FACT,
                content={"attached": False, "error": f"jsonl_sink import: {exc}"},
                schema_ref="sink.status.v1",
            )}

        sink = JsonlFileSink(Path(path), fsync=fsync)

        # Build observer that buffers + flushes
        buffer: list = []
        written_count = {"value": 0}

        def _flush_buffer():
            if not buffer:
                return
            sink.append_batch(list(buffer))
            written_count["value"] += len(buffer)
            buffer.clear()

        def _observer(_session, event):
            buffer.append(event)
            if mode == "simple" or len(buffer) >= batch_size:
                _flush_buffer()

        sess = get_session()
        cancel = sess.observe(_observer)

        # Register sink on the Session instance itself (scoped, NOT global).
        # flush_sink looks it up via the same Session.
        sink_name = cfg.get("name", "default")
        from agent_lab.nodes.session_log._sink import register_session_sink
        register_session_sink(sink_name, sink, _flush_buffer)

        return {"status": Artifact(
            kind=ArtifactKind.FACT,
            content={
                "attached": True,
                "name": sink_name,
                "path": str(path),
                "mode": mode,
                "batch_size": batch_size,
                "fsync": fsync,
                "written": written_count["value"],
                "cancel": cancel,
            },
            schema_ref="sink.status.v1",
        )}
