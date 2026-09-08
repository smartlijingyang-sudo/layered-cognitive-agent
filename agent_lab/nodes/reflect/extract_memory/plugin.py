"""extract_memory — passthrough that lets MemoryExtractPlugin decide candidates.

The 3-branch memory-candidate decision tree lives in
``agent_lab.plugins.memory_extract.MemoryExtractPlugin``. This node:

  1. Emits the reflection FACT unchanged (so the runner's existing
     on_reflection hook fan-out writes back to the store).
  2. Locally fans the same on_reflection event so the plugin's
     ``memory_candidates`` payload becomes available to emit alongside.

Backward-compat: when no MemoryExtractPlugin is configured, the node
emits an empty candidates list (same as the original node did when
the reflection had no fields).
"""

from __future__ import annotations

from agent_lab.nodes.base import Node
from agent_lab.nodes.manifest import (
    NodeKind,
    NodeLayer,
    PortInfo,
    PortKind,
    node,
)
from agent_lab.plugins import fanout_hooks
from agent_lab.plugins.base import GraphPlugin, HookContext, HookEvent
from agent_lab.primitives.artifact import Artifact, ArtifactKind


@node(
    id="extract_memory",
    name="extract_memory",
    layer=NodeLayer.PHASE,
    kind=NodeKind.TRANSFORMER,
    description=(
        "Passthrough that emits the reflection artifact. The memory-"
        "candidate decision tree lives in MemoryExtractPlugin (the "
        "on_reflection hook). When the plugin populates the "
        "memory_candidates payload, this node emits it as a separate "
        "artifact alongside the reflection."
    ),
    inputs=[
        PortInfo("reflection", kind=PortKind.FACT, required=False),
    ],
    outputs=[PortInfo("memory_candidates", kind=PortKind.FACT)],
    provides=["memory_extract"],
    emits=["memory_candidates"],
    relates_to=["call_critic", "write_extract"],
)
class ExtractMemoryNode(Node):
    """Passthrough — fan out on_reflection, emit candidates if the plugin sets them."""

    name = "extract_memory"

    def execute(self, node, inputs):
        out_port = node.outs[0] if node.outs else "memory_candidates"
        reflection_artifact = inputs.get("reflection")
        if reflection_artifact is None:
            return {
                out_port: Artifact(
                    kind=ArtifactKind.FACT,
                    content={"items": []},
                    schema_ref="memory.candidates.v1",
                )
            }

        # Run the on_reflection hook locally so the plugin can populate
        # payload["memory_candidates"]. The runner will also run the
        # same hook when the reflection artifact propagates; both calls
        # produce the same payload (the plugin is pure).
        ctx = HookContext(
            event=HookEvent.ON_REFLECTION,
            spec_id="",
            node_id=node.id,
            node_factory="extract_memory",
            artifact_digest=reflection_artifact.short_id(),
            payload={
                "artifact": reflection_artifact,
                "port_id": "reflection",
                "schema_ref": getattr(reflection_artifact, "schema_ref", "reflection.v1"),
            },
        )
        from agent_lab.nodes.base import NodeRegistry  # noqa: F401 — import guard

        # Resolve any registered reflection/memory plugins. Without
        # this helper the extract node would have to know about plugin
        # types directly; we use the same _plugins() shape the runner
        # uses, scoped to plugins bound to this node.
        plugins: list[GraphPlugin] = []
        try:
            # Walk the global plugin class registry for plugins bound to
            # this node by name or by kind (memory_extract).
            from agent_lab.plugins.base import get_plugin_class

            for kind in ("memory_extract",):
                cls = get_plugin_class(kind)
                if cls is None:
                    continue
                plugins.append(cls(name=f"_extract_{kind}", kind=kind))
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug("extract_memory plugin resolution: %s", exc)

        if plugins:
            ctx = fanout_hooks(plugins, HookEvent.ON_REFLECTION, ctx)

        candidates_payload = ctx.payload.get(
            "memory_candidates",
            {"items": []},
        )
        return {
            out_port: Artifact(
                kind=ArtifactKind.FACT,
                content=candidates_payload,
                schema_ref="memory.candidates.v1",
            )
        }
